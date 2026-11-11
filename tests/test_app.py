from pathlib import Path
import unittest
from unittest.mock import patch

import app as app_module
from atlas_chat import AtlasAPIError, AtlasSettings


class FlaskContractTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        app_module.limiter.reset()
        self.client = app_module.app.test_client()

    @patch("app.ask_atlas", return_value="Answer")
    def test_invalid_inputs_never_reach_model(self, ask_atlas):
        for route in ("/api/ask", "/api/chat", "/api/stream"):
            for payload in (["question"], {"query": "x" * 4001},
                            {"query": "Hello", "last_response": "x" * 16001},
                            {"query": "Hello", "last_response": []}):
                with self.subTest(route=route, payload_type=type(payload)):
                    response = self.client.post(route, json=payload)
                    self.assertEqual(response.status_code, 400)
        ask_atlas.assert_not_called()

    @patch("app.ask_atlas")
    def test_oversized_body_is_rejected(self, ask_atlas):
        response = self.client.post("/api/stream", json={"query": "x" * 70000})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["error"], "Request is too large.")
        ask_atlas.assert_not_called()

    @patch("app.ask_atlas", return_value="Answer")
    def test_rate_limit_is_shared_across_chat_endpoints(self, ask_atlas):
        routes = ("/api/ask", "/api/chat", "/api/stream")
        for index in range(10):
            response = self.client.post(routes[index % 3], json={"query": "Hi"})
            self.assertEqual(response.status_code, 200)
            response.get_data()
            response.close()
        response = self.client.post("/api/chat", json={"query": "Hi"},
                                    headers={"X-Forwarded-For": "1.2.3.4"})
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
        self.assertEqual(ask_atlas.call_count, 10)

    def test_default_cors_does_not_allow_arbitrary_websites(self):
        response = self.client.options("/api/chat", headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST"})
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    @patch("app.ask_atlas", side_effect=AtlasAPIError("internal secret details"))
    def test_upstream_errors_are_not_returned_to_clients(self, ask_atlas):
        for route in ("/api/ask", "/api/chat", "/api/stream"):
            response = self.client.post(route, json={"query": "Hi"})
            self.assertNotIn("internal secret details", response.get_data(as_text=True))
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_existing_web_routes_are_preserved(self):
        responses = [
            self.client.get("/"),
            self.client.get("/widget"),
            self.client.get("/assets/marked.js"),
            self.client.get("/assets/purify.min.js"),
            self.client.get("/assets/safe-markdown.js"),
            self.client.get("/embed.js"),
        ]
        try:
            self.assertEqual([response.status_code for response in responses], [200] * 6)
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
        self.assertNotIn("ATLAS unavailable", body)
        self.assertIn("temporarily unavailable", body)
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
