import unittest
import asyncio
import httpx
from datetime import datetime, timezone
from bson import ObjectId

from app.main import app, save_session_conversation
from app.db import admin_users_collection, leads_collection
from app.auth import create_access_token
from app.redis_client import get_redis


class TestT9HumanHandoffAndLeads(unittest.TestCase):
    def test_handoff_and_leads_flow(self):
        async def run_tests():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                owner = await admin_users_collection.find_one({"role": "business_owner", "is_active": True})
                self.assertIsNotNone(owner, "Active business owner required in DB")
                tenant_id = owner["tenant_id"]
                api_key = owner["api_key"]
                owner_token = create_access_token(owner)

                # Clean up existing test leads
                await leads_collection.delete_many({"tenant_id": tenant_id})

                # Clear rate limit keys in Redis for clean test
                r = get_redis()
                await r.delete("ratelimit:handoff:127.0.0.1")
                await r.delete("ratelimit:handoff:198.51.100.1")

                session_id = "test_session_t9_123"

                # -------------------------------------------------------------
                # 1. Test gating: handoff_enabled flag (default False -> 403)
                # -------------------------------------------------------------
                await admin_users_collection.update_one(
                    {"_id": owner["_id"]},
                    {"$set": {"bot_config.handoff_enabled": False}},
                )

                resp_gated = await client.post(
                    "/api/handoff",
                    headers={"X-API-Key": api_key, "X-Forwarded-For": "198.51.100.1"},
                    json={
                        "session_id": session_id,
                        "name": "Anil Kumar",
                        "email": "anil@example.com",
                        "phone": "9876543210",
                        "message": "Need urgent doctor consultation",
                    },
                )
                self.assertEqual(resp_gated.status_code, 403, "Must return 403 when handoff_enabled is False")

                # Enable handoff for tenant
                await admin_users_collection.update_one(
                    {"_id": owner["_id"]},
                    {"$set": {"bot_config.handoff_enabled": True}},
                )

                # -------------------------------------------------------------
                # 2. Store 15 messages in session to test 10-message limit
                # -------------------------------------------------------------
                fake_history = [
                    {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message number {i}"}
                    for i in range(15)
                ]
                await save_session_conversation(f"{tenant_id}:{session_id}", fake_history)

                # -------------------------------------------------------------
                # 3. Successful Lead Capture (stores last 10 messages)
                # -------------------------------------------------------------
                resp_create = await client.post(
                    "/api/handoff",
                    headers={"X-API-Key": api_key, "X-Forwarded-For": "198.51.100.1"},
                    json={
                        "session_id": session_id,
                        "name": "Anil Kumar",
                        "email": "anil@example.com",
                        "phone": "9876543210",
                        "message": "=1+1 Formula Injection Test",
                    },
                )
                self.assertEqual(resp_create.status_code, 200, resp_create.text)
                lead_data = resp_create.json()
                self.assertEqual(lead_data["status"], "ok")
                lead_id = lead_data["lead_id"]

                # Verify in MongoDB: lead exists and has exactly 10 chat messages
                lead_in_db = await leads_collection.find_one({"_id": ObjectId(lead_id)})
                self.assertIsNotNone(lead_in_db)
                self.assertEqual(lead_in_db["name"], "Anil Kumar")
                self.assertEqual(lead_in_db["status"], "new")
                self.assertEqual(len(lead_in_db["chat_history"]), 10)
                # Ensure it captured the last 10 (messages 5 to 14)
                self.assertEqual(lead_in_db["chat_history"][0]["content"], "Message number 5")
                self.assertEqual(lead_in_db["chat_history"][-1]["content"], "Message number 14")

                # -------------------------------------------------------------
                # 4. Strict per-IP rate limiting (3/hour)
                # -------------------------------------------------------------
                # We already used 1 request from 198.51.100.1. Send 2 more (total 3):
                for idx in [2, 3]:
                    r2 = await client.post(
                        "/api/handoff",
                        headers={"X-API-Key": api_key, "X-Forwarded-For": "198.51.100.1"},
                        json={
                            "session_id": f"sess_{idx}",
                            "name": f"User {idx}",
                            "email": f"user{idx}@example.com",
                        },
                    )
                    self.assertEqual(r2.status_code, 200)

                # The 4th request from the same IP MUST be rejected with 429
                r4 = await client.post(
                    "/api/handoff",
                    headers={"X-API-Key": api_key, "X-Forwarded-For": "198.51.100.1"},
                    json={
                        "session_id": "sess_4",
                        "name": "User 4",
                        "email": "user4@example.com",
                    },
                )
                self.assertEqual(r4.status_code, 429, "4th request within 1hr from same IP must be rate-limited with 429")

                # -------------------------------------------------------------
                # 5. Admin Leads Listing & Pagination
                # -------------------------------------------------------------
                resp_list = await client.get(
                    "/api/admin/leads?status=all",
                    headers={"Authorization": f"Bearer {owner_token}"},
                )
                self.assertEqual(resp_list.status_code, 200)
                list_data = resp_list.json()
                self.assertEqual(list_data["total"], 3)
                self.assertEqual(list_data["counts"]["new"], 3)
                self.assertEqual(len(list_data["items"]), 3)

                # -------------------------------------------------------------
                # 6. Admin Update Lead Status
                # -------------------------------------------------------------
                resp_patch = await client.patch(
                    f"/api/admin/leads/{lead_id}",
                    headers={"Authorization": f"Bearer {owner_token}"},
                    json={"status": "contacted"},
                )
                self.assertEqual(resp_patch.status_code, 200)
                self.assertEqual(resp_patch.json()["status"], "contacted")

                updated_lead = await leads_collection.find_one({"_id": ObjectId(lead_id)})
                self.assertEqual(updated_lead["status"], "contacted")

                # -------------------------------------------------------------
                # 7. CSV Export & Formula Injection Sanitization
                # -------------------------------------------------------------
                resp_csv = await client.get(
                    "/api/admin/leads/export.csv",
                    headers={"Authorization": f"Bearer {owner_token}"},
                )
                self.assertEqual(resp_csv.status_code, 200)
                self.assertIn("text/csv", resp_csv.headers["content-type"])
                csv_content = resp_csv.text
                self.assertIn("Lead ID,Created At (UTC),Name", csv_content)
                self.assertIn("Anil Kumar", csv_content)
                # Verify formula injection was neutralized with prefix quote
                self.assertIn("'=1+1 Formula Injection Test", csv_content)

                # Clean up
                await leads_collection.delete_many({"tenant_id": tenant_id})

        asyncio.run(run_tests())


if __name__ == "__main__":
    unittest.main()
