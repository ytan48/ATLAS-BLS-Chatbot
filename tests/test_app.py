from pathlib import Path
import unittest
from unittest.mock import patch

import app as app_module
from atlas_chat import AtlasAPIError, AtlasSettings


class FlaskContractTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def test_existing_web_routes_are_preserved(self):
        responses = [
            self.client.get("/"),
            self.client.get("/widget"),
            self.client.get("/embed.js"),
        ]
        try:
            self.assertEqual([response.status_code for response in responses], [200] * 3)
            self.assertIn("javascript", responses[-1].content_type)
        finally:
            for response in responses:
                response.close()

    def test_empty_query_is_rejected(self):
        response = self.client.post("/api/ask", json={"query": ""})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "No query provided"})

    @patch("app.ask_atlas", return_value="ATLAS answer")
    def test_chat_route_keeps_existing_response_contract(self, ask_atlas):
        response = self.client.post(
            "/api/chat",
            json={"query": "Question", "last_response": "Earlier answer"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["answer"], "ATLAS answer")
        self.assertEqual(
            response.get_json()["pipeline"], "atlas_single_completion"
        )
        ask_atlas.assert_called_once_with(
            "Question", last_response="Earlier answer"
        )

    @patch("app.ask_atlas", return_value="Streamed ATLAS answer")
    def test_stream_route_keeps_sse_contract(self, ask_atlas):
        response = self.client.post("/api/stream", json={"query": "Question"})
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "agent_status"', body)
        self.assertIn("BLS instructions and knowledge base", body)
        self.assertIn('"content": "Streamed ATLAS answer"', body)
        self.assertIn('"type": "done"', body)
        ask_atlas.assert_called_once_with("Question", last_response="")

    @patch("app.ask_atlas", side_effect=AtlasAPIError("ATLAS unavailable"))
    def test_stream_route_emits_error_event(self, ask_atlas):
        response = self.client.post("/api/stream", json={"query": "Question"})
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "error"', body)
        self.assertIn("ATLAS unavailable", body)
        self.assertIn('"type": "done"', body)

    @patch("app.AtlasSettings.from_env")
    def test_public_config_never_exposes_key(self, from_env):
        from_env.return_value = AtlasSettings(
            api_key="must-not-leak",
            model="qwen-test",
            instructions_file=Path("instructions.txt"),
            knowledge_base_file=Path("knowledgebase.md"),
        )

        response = self.client.get("/api/config")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["api_key_configured"])
        self.assertNotIn("api_key", body)
        self.assertNotIn("must-not-leak", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
