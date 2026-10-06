import unittest
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from app.main import app, record_daily_usage, get_current_ist_date, IST
from app.db import admin_users_collection, usage_daily_collection
from app.auth import create_access_token


class TestT7UsageAndQuotas(unittest.TestCase):
    def test_usage_and_quota_flow(self):
        async def run_tests():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                owner = await admin_users_collection.find_one({"role": "business_owner", "is_active": True})
                self.assertIsNotNone(owner, "Active business owner required in DB")
                tenant_id = owner["tenant_id"]
                api_key = owner["api_key"]
                owner_token = create_access_token(owner)

                super_admin = await admin_users_collection.find_one({"role": "super_admin"})
                self.assertIsNotNone(super_admin, "Super admin required in DB")
                super_admin_token = create_access_token(super_admin)

                today_ist = get_current_ist_date()

                # Cleanup test tenant's daily usage for clean test run
                await usage_daily_collection.delete_many({"tenant_id": tenant_id})

                # ---------------------------------------------------------
                # 1. Concurrency Test for record_daily_usage
                # ---------------------------------------------------------
                concurrency_count = 15
                tasks = [
                    record_daily_usage(
                        tenant_id=tenant_id,
                        messages=1,
                        tool_calls=2,
                        user_text="What is blood test?",
                        bot_text="Blood test details...",
                    )
                    for _ in range(concurrency_count)
                ]
                await asyncio.gather(*tasks)

                doc = await usage_daily_collection.find_one({"tenant_id": tenant_id, "date": today_ist})
                self.assertIsNotNone(doc, "Daily usage document must exist")
                self.assertEqual(
                    doc["messages"],
                    concurrency_count,
                    f"Expected {concurrency_count} messages, got {doc['messages']} (atomic increment check)",
                )
                self.assertEqual(
                    doc["tool_calls"],
                    concurrency_count * 2,
                    f"Expected {concurrency_count * 2} tool calls, got {doc['tool_calls']}",
                )
                self.assertTrue(doc.get("estimated_tokens", False))

                # ---------------------------------------------------------
                # 2. GET /api/admin/usage
                # ---------------------------------------------------------
                res_usage = await client.get(
                    "/api/admin/usage",
                    headers={"Authorization": f"Bearer {owner_token}"},
                )
                self.assertEqual(res_usage.status_code, 200)
                data = res_usage.json()
                self.assertEqual(data["tenant_id"], tenant_id)
                self.assertIn("records", data)
                self.assertIn("summary", data)
                self.assertEqual(data["summary"]["total_messages"], concurrency_count)
                self.assertEqual(data["summary"]["total_tool_calls"], concurrency_count * 2)

                # ---------------------------------------------------------
                # 3. Superadmin PUT /api/superadmin/tenants/{id}/limits
                # ---------------------------------------------------------
                res_limits = await client.put(
                    f"/api/superadmin/tenants/{tenant_id}/limits",
                    headers={"Authorization": f"Bearer {super_admin_token}"},
                    json={"daily_message_limit": 10, "monthly_message_limit": 500},
                )
                self.assertEqual(res_limits.status_code, 200)
                limits_data = res_limits.json()
                self.assertEqual(limits_data["daily_message_limit"], 10)
                self.assertEqual(limits_data["monthly_message_limit"], 500)

                # Verify in database
                owner_updated = await admin_users_collection.find_one({"tenant_id": tenant_id})
                self.assertEqual(owner_updated["daily_message_limit"], 10)
                self.assertEqual(owner_updated["monthly_message_limit"], 500)

                # ---------------------------------------------------------
                # 4. Quota Enforcement in POST /chat (HTTP 429 QUOTA_EXCEEDED)
                # ---------------------------------------------------------
                # Since today's messages (15) >= daily_message_limit (10),
                # /chat must reject BEFORE streaming starts with 429
                res_chat_blocked = await client.post(
                    "/chat",
                    headers={"X-API-Key": api_key},
                    json={"session_id": "test-quota-session", "message": "Hello?"},
                )
                self.assertEqual(res_chat_blocked.status_code, 429)
                self.assertIn("QUOTA_EXCEEDED", res_chat_blocked.json()["detail"])

                # Reset limits so existing tenant continues functioning freely
                await client.put(
                    f"/api/superadmin/tenants/{tenant_id}/limits",
                    headers={"Authorization": f"Bearer {super_admin_token}"},
                    json={"daily_message_limit": None, "monthly_message_limit": None},
                )

                # Clean up test usage
                await usage_daily_collection.delete_many({"tenant_id": tenant_id})

        asyncio.run(run_tests())


if __name__ == "__main__":
    unittest.main()
