import unittest
import asyncio
import httpx
from app.main import app
from app.db import admin_users_collection, feedback_collection

class TestFeedback(unittest.TestCase):
    def test_feedback_flow(self):
        async def run_tests():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                owner = await admin_users_collection.find_one({"role": "business_owner", "is_active": True})
                self.assertIsNotNone(owner, "Active business owner required in DB")
                api_key = owner["api_key"]
                tenant_id = owner["tenant_id"]

                # 1. Missing API key rejected
                r_no_key = await client.post("/api/feedback", json={
                    "session_id": "test-session-1",
                    "message_id": "msg-test-1",
                    "rating": "up"
                })
                self.assertEqual(r_no_key.status_code, 401)

                # 2. Invalid rating rejected
                r_invalid = await client.post(
                    "/api/feedback",
                    headers={"X-API-Key": api_key},
                    json={
                        "session_id": "test-session-1",
                        "message_id": "msg-test-1",
                        "rating": "neutral"
                    }
                )
                self.assertEqual(r_invalid.status_code, 422)

                # 3. Valid thumbs up
                msg_id = "msg-feedback-test-456"
                r_valid = await client.post(
                    "/api/feedback",
                    headers={"X-API-Key": api_key},
                    json={
                        "session_id": "test-session-1",
                        "message_id": msg_id,
                        "rating": "up",
                        "comment": "Accurate response",
                        "user_question": "What is hemoglobin normal range?",
                        "bot_answer": "Normal range is 13.8 to 17.2 g/dL."
                    }
                )
                self.assertEqual(r_valid.status_code, 200)
                self.assertEqual(r_valid.json()["rating"], "up")

                # Verify in DB
                db_doc = await feedback_collection.find_one({"tenant_id": tenant_id, "message_id": msg_id})
                self.assertIsNotNone(db_doc)
                self.assertEqual(db_doc["rating"], "up")
                self.assertEqual(db_doc["comment"], "Accurate response")
                self.assertEqual(db_doc["user_question"], "What is hemoglobin normal range?")

                # 4. Upsert (change rating to down on same message)
                r_update = await client.post(
                    "/api/feedback",
                    headers={"X-API-Key": api_key},
                    json={
                        "session_id": "test-session-1",
                        "message_id": msg_id,
                        "rating": "down",
                        "comment": "Needs more detail"
                    }
                )
                self.assertEqual(r_update.status_code, 200)
                self.assertEqual(r_update.json()["rating"], "down")

                # Verify updated in DB, not duplicated
                count = await feedback_collection.count_documents({"tenant_id": tenant_id, "message_id": msg_id})
                self.assertEqual(count, 1)
                db_doc_updated = await feedback_collection.find_one({"tenant_id": tenant_id, "message_id": msg_id})
                self.assertEqual(db_doc_updated["rating"], "down")
                self.assertEqual(db_doc_updated["comment"], "Needs more detail")

                # Clean up
                await feedback_collection.delete_one({"tenant_id": tenant_id, "message_id": msg_id})

        asyncio.run(run_tests())

if __name__ == "__main__":
    unittest.main()
