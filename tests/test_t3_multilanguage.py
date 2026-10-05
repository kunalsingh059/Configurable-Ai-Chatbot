import unittest
from app.groq_client import build_system_prompt, LANGUAGE_PROMPT_INSTRUCTION, TONE_INSTRUCTIONS

class TestMultiLanguageAndTone(unittest.TestCase):
    def test_default_prompt_includes_language_instruction(self):
        prompt = build_system_prompt(tenant_tools=[], documents_context="")
        self.assertIn("Language and Script Style Guidelines", prompt)
        self.assertIn("Hinglish", prompt)
        self.assertIn("Devanagari", prompt)
        self.assertIn("Tone: Maintain a warm, friendly", prompt)

    def test_reply_in_user_language_disabled(self):
        prompt = build_system_prompt(
            tenant_tools=[],
            documents_context="",
            bot_config={"reply_in_user_language": False}
        )
        self.assertNotIn("Language and Script Style Guidelines", prompt)

    def test_tone_customization(self):
        prompt_prof = build_system_prompt(
            tenant_tools=[],
            documents_context="",
            bot_config={"tone": "professional"}
        )
        self.assertIn("polished, professional", prompt_prof)

        prompt_cas = build_system_prompt(
            tenant_tools=[],
            documents_context="",
            bot_config={"tone": "casual"}
        )
        self.assertIn("relaxed, easygoing", prompt_cas)

if __name__ == "__main__":
    unittest.main()
