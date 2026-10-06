import unittest
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from app.main import app, record_daily_usage, get_current_ist_date, IST
from app.db import (
    admin_users_collection,
    usage_daily_collection,
    feedback_collection,
    unanswered_collection,
)
from app.auth import create_access_token


class TestT8AnalyticsDashboard(unittest.TestCase):
    def test_analytics_dashboard_flow(self):
        async def run_tests():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                owner = await admin_users_collection.find_one({"role": "business_owner", "is_active": True})
                self.assertIsNotNone(owner, "Active business owner required in DB")
                tenant_id = owner["tenant_id"]
                owner_token = create_access_token(owner)

                today_dt = datetime.now(IST)
                today_date = today_dt.date()
                today_str = today_date.strftime("%Y-%m-%d")
                yesterday_str = (today_date - timedelta(days=1)).strftime("%Y-%m-%d")

                # Clean up tenant data for reliable test run
                await usage_daily_collection.delete_many({"tenant_id": tenant_id})
                await feedback_collection.delete_many({"tenant_id": tenant_id})
                await unanswered_collection.delete_many({"tenant_id": tenant_id})

                # -------------------------------------------------------------
                # 1. Seed usage_daily_collection (T8 reads strictly from this)
                # -------------------------------------------------------------
                await usage_daily_collection.insert_one({
                    "tenant_id": tenant_id,
                    "date": today_str,
                    "messages": 12,
                    "sessions": 4,
                    "tool_calls": 3,
                    "input_tokens": 100,
                    "output_tokens": 150,
                    "fallback_count": 0,
                })
                await usage_daily_collection.insert_one({
                    "tenant_id": tenant_id,
                    "date": yesterday_str,
                    "messages": 8,
                    "sessions": 2,
                    "tool_calls": 1,
                    "input_tokens": 80,
                    "output_tokens": 120,
                    "fallback_count": 0,
                })

                # -------------------------------------------------------------
                # 2. Seed feedback_collection (3 up, 1 down -> 75.0% satisfaction)
                # -------------------------------------------------------------
                now_utc = datetime.now(timezone.utc)
                for i in range(3):
                    await feedback_collection.insert_one({
                        "tenant_id": tenant_id,
                        "message_id": f"msg_up_{i}",
                        "rating": "up",
                        "created_at": now_utc,
                    })
                await feedback_collection.insert_one({
                    "tenant_id": tenant_id,
                    "message_id": "msg_down_0",
                    "rating": "down",
                    "created_at": now_utc,
                })

                # -------------------------------------------------------------
                # 3. Seed unanswered_collection (2 open, 1 resolved)
                # -------------------------------------------------------------
                await unanswered_collection.insert_one({
                    "tenant_id": tenant_id,
                    "question": "Can I get home visit for test?",
                    "status": "open",
                    "created_at": now_utc,
                    "timestamp": now_utc,
                })
                await unanswered_collection.insert_one({
                    "tenant_id": tenant_id,
                    "question": "What is the price of MRI?",
                    "status": "open",
                    "created_at": now_utc,
                    "timestamp": now_utc,
                })
                await unanswered_collection.insert_one({
                    "tenant_id": tenant_id,
                    "question": "Do you accept card?",
                    "status": "resolved",
                    "created_at": now_utc,
                    "timestamp": now_utc,
                })

                # -------------------------------------------------------------
                # 4. Test unauthorized request
                # -------------------------------------------------------------
                resp_unauth = await client.get("/api/admin/analytics")
                self.assertEqual(resp_unauth.status_code, 401)

                # -------------------------------------------------------------
                # 5. Test 7d range
                # -------------------------------------------------------------
                resp_7d = await client.get(
                    "/api/admin/analytics?range=7d",
                    headers={"Authorization": f"Bearer {owner_token}"},
                )
                self.assertEqual(resp_7d.status_code, 200, resp_7d.text)
                data_7d = resp_7d.json()

                self.assertEqual(data_7d["tenant_id"], tenant_id)
                self.assertEqual(data_7d["range"], "7d")
                self.assertEqual(len(data_7d["daily_series"]), 7)

                tiles = data_7d["tiles"]
                # Conversations tile (distinct sessions)
                self.assertEqual(tiles["conversations"], 6)  # 4 today + 2 yesterday
                # Messages tile
                self.assertEqual(tiles["messages"], 20)      # 12 today + 8 yesterday
                # Satisfaction tile
                self.assertEqual(tiles["satisfaction_pct"], 75.0)
                self.assertEqual(tiles["thumbs_up"], 3)
                self.assertEqual(tiles["thumbs_down"], 1)
                # Unanswered tile
                self.assertEqual(tiles["unanswered_open"], 2)

                # -------------------------------------------------------------
                # 6. Test 30d range
                # -------------------------------------------------------------
                resp_30d = await client.get(
                    "/api/admin/analytics?range=30d",
                    headers={"Authorization": f"Bearer {owner_token}"},
                )
                self.assertEqual(resp_30d.status_code, 200)
                data_30d = resp_30d.json()
                self.assertEqual(data_30d["range"], "30d")
                self.assertEqual(len(data_30d["daily_series"]), 30)
                self.assertEqual(data_30d["tiles"]["messages"], 20)

                # Clean up
                await usage_daily_collection.delete_many({"tenant_id": tenant_id})
                await feedback_collection.delete_many({"tenant_id": tenant_id})
                await unanswered_collection.delete_many({"tenant_id": tenant_id})

        asyncio.run(run_tests())


if __name__ == "__main__":
    unittest.main()
