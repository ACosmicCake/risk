import unittest
from unittest.mock import patch, mock_open
import os

# Set dummy API keys for testing purposes BEFORE importing the interfaces
os.environ["OPENAI_API_KEY"] = "test_openai_key"
os.environ["GOOGLE_API_KEY"] = "test_google_key"
os.environ["ANTHROPIC_API_KEY"] = "test_anthropic_key"
os.environ["DEEPSEEK_API_KEY"] = "test_deepseek_key"

from risk.llm.interface import LLMInterface
from risk.llm.chatgpt import ChatGPTInterface
from risk.llm.gemini import GeminiInterface
from risk.llm.claude import ClaudeInterface
from risk.llm.deepseek import DeepseekInterface

class TestLLMInterfaces(unittest.TestCase):

    def _test_interface_instantiation_and_get_decision(self, InterfaceClass, expected_key_name):
        """Helper method to test instantiation and get_decision for an interface."""
        # Test successful instantiation
        interface = InterfaceClass()
        self.assertIsInstance(interface, LLMInterface)
        self.assertIsNotNone(getattr(interface, 'api_key', None) or getattr(interface, 'api_url', None)) # Deepseek might just store URL + key

        # Test get_decision placeholder
        prompt = "Test prompt"
        game_state = {"phase": "reinforce", "player": "Player1"}
        decision = interface.get_decision(prompt, game_state)

        self.assertIsInstance(decision, dict)
        self.assertIn("thoughts", decision)
        self.assertIn("actions", decision)
        self.assertIn("chat", decision)
        self.assertIsInstance(decision["actions"], list)
        self.assertIsInstance(decision["chat"], dict)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "fake_key_for_test"})
    def test_chatgpt_interface(self):
        self._test_interface_instantiation_and_get_decision(ChatGPTInterface, "OPENAI_API_KEY")

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}) # Test missing key
    def test_chatgpt_interface_missing_key(self):
        with self.assertRaises(ValueError) as context:
            ChatGPTInterface()
        self.assertTrue("OPENAI_API_KEY not found" in str(context.exception))

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "fake_key_for_test"})
    def test_gemini_interface(self):
        self._test_interface_instantiation_and_get_decision(GeminiInterface, "GOOGLE_API_KEY")

    @patch.dict(os.environ, {"GOOGLE_API_KEY": ""})
    def test_gemini_interface_missing_key(self):
        with self.assertRaises(ValueError) as context:
            GeminiInterface()
        self.assertTrue("GOOGLE_API_KEY not found" in str(context.exception))

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake_key_for_test"})
    def test_claude_interface(self):
        self._test_interface_instantiation_and_get_decision(ClaudeInterface, "ANTHROPIC_API_KEY")

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
    def test_claude_interface_missing_key(self):
        with self.assertRaises(ValueError) as context:
            ClaudeInterface()
        self.assertTrue("ANTHROPIC_API_KEY not found" in str(context.exception))

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake_key_for_test"})
    def test_deepseek_interface(self):
        self._test_interface_instantiation_and_get_decision(DeepseekInterface, "DEEPSEEK_API_KEY")

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""})
    def test_deepseek_interface_missing_key(self):
        with self.assertRaises(ValueError) as context:
            DeepseekInterface()
        self.assertTrue("DEEPSEEK_API_KEY not found" in str(context.exception))

if __name__ == '__main__':
    # Clean up environment variables set at the top of the file after tests run
    del os.environ["OPENAI_API_KEY"]
    del os.environ["GOOGLE_API_KEY"]
    del os.environ["ANTHROPIC_API_KEY"]
    del os.environ["DEEPSEEK_API_KEY"]
    unittest.main()
