import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from atlas_chat import (
    AtlasAPIError,
    AtlasConfigurationError,
    AtlasSettings,
    ask_atlas,
    build_payload,
    extract_answer,
    load_system_prompt,
)


class FakeResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


class AtlasChatTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.instructions = root / "instructions.txt"
        self.knowledge_base = root / "knowledgebase.md"
        self.instructions.write_text("Follow the BLS knowledge base.", encoding="utf-8")
        self.knowledge_base.write_text("# BLS\nTuition is documented here.", encoding="utf-8")
        self.settings = AtlasSettings(
            api_key="test-secret",
            api_url="https://atlas.example/v1/chat/completions",
            model="qwen-test",
            temperature=0.2,
            reasoning_effort="medium",
            use_last_response=True,
            instructions_file=self.instructions,
            knowledge_base_file=self.knowledge_base,
            timeout_seconds=17,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_system_prompt_concatenates_reference_files(self):
        self.assertEqual(
            load_system_prompt(self.settings),
            "Follow the BLS knowledge base.\n# BLS\nTuition is documented here.",
        )

    def test_build_payload_matches_reference_cli_shape(self):
        payload = build_payload(
            "What is tuition?",
            self.settings,
            last_response="Previous answer",
        )

        self.assertEqual(payload["model"], "qwen-test")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["reasoning_effort"], "medium")
        self.assertEqual(
            [message["role"] for message in payload["messages"]],
            ["system", "assistant", "user"],
        )
        self.assertEqual(payload["messages"][-1]["content"], "What is tuition?")

    @patch("atlas_chat.urllib.request.urlopen")
    def test_ask_atlas_sends_bearer_request_and_extracts_answer(self, urlopen):
        urlopen.return_value = FakeResponse(
            {"choices": [{"message": {"content": "BLS answer"}}]}
        )

        answer = ask_atlas(
            "What is tuition?",
            last_response="Previous answer",
            settings=self.settings,
        )

        self.assertEqual(answer, "BLS answer")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, self.settings.api_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 17)
        sent = json.loads(request.data.decode("utf-8"))
        self.assertNotIn("api_key", sent)
        self.assertNotIn("course_name", sent)
        self.assertNotIn("retrieval_only", sent)
        self.assertEqual(sent["messages"][1]["role"], "assistant")

    def test_extract_answer_rejects_invalid_response(self):
        with self.assertRaises(AtlasAPIError):
            extract_answer({"message": "not OpenAI-compatible"})

    def test_settings_validation_rejects_unknown_reasoning_effort(self):
        invalid = AtlasSettings(
            api_key="test",
            reasoning_effort="ultra",
            instructions_file=self.instructions,
            knowledge_base_file=self.knowledge_base,
        )
        with self.assertRaises(AtlasConfigurationError):
            invalid.validate()


if __name__ == "__main__":
    unittest.main()
