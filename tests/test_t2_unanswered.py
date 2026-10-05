import unittest
import asyncio
import httpx
from datetime import datetime, timezone
from app.main import app, log_unanswered_question
from app.db import admin_users_collection, unanswered_collection
from app.auth import create_access_token

class TestUnansweredQuestions(unittest.TestCase):
    def test_unanswered_questions_lifecycle(self):
        async def run_tests():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                owner = await admin_users_collection.find_one({"role": "business_owner", "is_active": True})
                self.assertIsNotNone(owner, "Active business owner required in DB")
                token = create_access_token(owner)
                auth_headers = {"Authorization": f"Bearer {token}"}
                tenant_id = owner["tenant_id"]

                # 1. Unauthenticated request rejected
                r_unauth = await client.get("/api/admin/unanswered")
                self.assertEqual(r_unauth.status_code, 401)

                # 2. Log an unanswered question for this tenant
                test_q = "Do you have gluten-free chocolate cake?"
                await log_unanswered_question(
                    tenant_id=tenant_id,
                    question=test_q,
                    session_id="session-test-unans",
                    reason="no_matching_docs_or_tools"
                )

                # 3. Retrieve open unanswered questions
                r_list = await client.get("/api/admin/unanswered?status=open", headers=auth_headers)
                self.assertEqual(r_list.status_code, 200)
                data = r_list.json()
                self.assertIn("items", data)
                self.assertGreaterEqual(data["total"], 1)

                found_item = next((i for i in data["items"] if i["question"] == test_q), None)
                self.assertIsNotNone(found_item, "Logged question must appear in open list")
                self.assertEqual(found_item["status"], "open")
                self.assertEqual(found_item["reason"], "no_matching_docs_or_tools")
                item_id = found_item["id"]

                # 4. Resolve the question
                r_patch = await client.patch(
                    f"/api/admin/unanswered/{item_id}",
                    headers=auth_headers,
                    json={"status": "resolved"}
                )
                self.assertEqual(r_patch.status_code, 200)
                self.assertEqual(r_patch.json()["status"], "resolved")

                # Verify now in resolved list
                r_resolved = await client.get("/api/admin/unanswered?status=resolved", headers=auth_headers)
                resolved_items = r_resolved.json()["items"]
                resolved_match = next((i for i in resolved_items if i["id"] == item_id), None)
                self.assertIsNotNone(resolved_match)
                self.assertEqual(resolved_match["status"], "resolved")

                # 5. Multi-tenancy check: another tenant token cannot see or edit this item
                fake_other_owner = {
                    "username": "other_owner_test",
                    "role": "business_owner",
                    "tenant_id": "other-tenant-999"
                }
                other_token = create_access_token(fake_other_owner)
                other_headers = {"Authorization": f"Bearer {other_token}"}

                # Other tenant should get 403 (deactivated/nonexistent in DB check)
                r_other_patch = await client.patch(
                    f"/api/admin/unanswered/{item_id}",
                    headers=other_headers,
                    json={"status": "ignored"}
                )
                self.assertEqual(r_other_patch.status_code, 403)

                # Clean up
                await unanswered_collection.delete_one({"_id": found_item["id"], "tenant_id": tenant_id})
                from bson import ObjectId
                await unanswered_collection.delete_one({"_id": ObjectId(item_id), "tenant_id": tenant_id})

        asyncio.run(run_tests())

if __name__ == "__main__":
    unittest.main()
