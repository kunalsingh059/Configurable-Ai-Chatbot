import unittest
import asyncio
import httpx
from pydantic import ValidationError
from app.main import app
from app.models import BotConfigModel
from app.db import admin_users_collection
from app.auth import create_access_token

class TestBotConfig(unittest.TestCase):
    def test_bot_config_model_validation(self):
        # 1. Valid config
        valid = BotConfigModel(
            bot_name="Dental Care Assistant",
            welcome_message="Hello! How can we assist your dental inquiry today?",
            primary_color="#2563eb",
            avatar_url="https://example.com/avatar.png",
            tone="professional",
            quick_replies=["Book Consultation", "Clinic Timings"],
            reply_in_user_language=True
        )
        self.assertEqual(valid.primary_color, "#2563eb")
        self.assertEqual(valid.tone, "professional")
        self.assertEqual(len(valid.quick_replies), 2)

        # 2. Invalid hex color
        with self.assertRaises(ValidationError):
            BotConfigModel(primary_color="blue")

        with self.assertRaises(ValidationError):
            BotConfigModel(primary_color="#12345")

        # 3. Invalid tone
        with self.assertRaises(ValidationError):
            BotConfigModel(tone="sarcastic")

        # 4. Avatar URL not starting with https://
        with self.assertRaises(ValidationError):
            BotConfigModel(avatar_url="http://insecure.com/avatar.png")

        # 5. Quick reply exceeding 40 chars
        with self.assertRaises(ValidationError):
            BotConfigModel(quick_replies=["A" * 45])

    def test_bot_config_endpoints(self):
        async def run_tests():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                owner = await admin_users_collection.find_one({"role": "business_owner", "is_active": True})
                self.assertIsNotNone(owner, "Active business owner required in DB")
                api_key = owner["api_key"]
                tenant_id = owner["tenant_id"]
                token = create_access_token(owner)

                # 1. Unauthorized GET /admin/bot-config
                r_unauth = await client.get("/admin/bot-config")
                self.assertEqual(r_unauth.status_code, 401)

                # 2. Authenticated GET /admin/bot-config
                r_get = await client.get("/admin/bot-config", headers={"Authorization": f"Bearer {token}"})
                self.assertEqual(r_get.status_code, 200)
                data = r_get.json()
                self.assertIn("bot_name", data)
                self.assertIn("welcome_message", data)
                self.assertIn("primary_color", data)
                self.assertIn("tone", data)
                self.assertIn("quick_replies", data)

                # 3. PUT /admin/bot-config with valid customization
                update_payload = {
                    "bot_name": "Premium Care AI",
                    "welcome_message": "Welcome! We are ready to help.",
                    "primary_color": "#4f46e5",
                    "avatar_url": "https://example.com/logo.png",
                    "tone": "friendly",
                    "quick_replies": ["Check Pricing", "Contact Support"],
                    "reply_in_user_language": True,
                }
                r_put = await client.put(
                    "/admin/bot-config",
                    headers={"Authorization": f"Bearer {token}"},
                    json=update_payload
                )
                self.assertEqual(r_put.status_code, 200)
                updated_data = r_put.json()
                self.assertEqual(updated_data["bot_name"], "Premium Care AI")
                self.assertEqual(updated_data["primary_color"], "#4f46e5")
                self.assertEqual(updated_data["quick_replies"], ["Check Pricing", "Contact Support"])

                # 4. GET /widget/config returns updated branding
                r_widget = await client.get("/widget/config", headers={"X-API-Key": api_key})
                self.assertEqual(r_widget.status_code, 200)
                widget_data = r_widget.json()
                self.assertEqual(widget_data["bot_name"], "Premium Care AI")
                self.assertEqual(widget_data["primary_color"], "#4f46e5")
                self.assertEqual(widget_data["avatar_url"], "https://example.com/logo.png")
                self.assertEqual(widget_data["welcome_message"], "Welcome! We are ready to help.")
                self.assertEqual(widget_data["quick_replies"], ["Check Pricing", "Contact Support"])

                # 5. Invalid hex in PUT /admin/bot-config returns 422
                r_invalid = await client.put(
                    "/admin/bot-config",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"primary_color": "not-a-color"}
                )
                self.assertEqual(r_invalid.status_code, 422)

        asyncio.run(run_tests())

if __name__ == "__main__":
    unittest.main()
