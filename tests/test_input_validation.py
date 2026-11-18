"""Offline input contract tests; never contact the inference server."""
import json
import unittest
from unittest.mock import patch

import app as app_module
from atlas_chat import AtlasSettings, build_payload
from input_dataset import SCENARIOS, make_scenario, metrics

ROUTES = ('/api/ask', '/api/chat', '/api/stream')

class InputValidationTests(unittest.TestCase):
    def setUp(self):
        self.config = patch.dict(app_module.app.config, TESTING=True)
        self.config.start()
        self.addCleanup(self.config.stop)
        self.addCleanup(app_module.limiter.reset)
        self.client = app_module.app.test_client()
        network = patch('atlas_chat.urllib.request.urlopen', side_effect=AssertionError('network forbidden'))
        network.start()
        self.addCleanup(network.stop)

    def check_request(self, route, payload, status, error=None):
        app_module.limiter.reset()
        with patch('app.ask_atlas', return_value='Synthetic answer') as model:
            response = self.client.post(route, json=payload, buffered=True)
            self.addCleanup(response.close)
            self.assertEqual(response.status_code, status)
            if status == 200:
                self.assertIn('Synthetic answer', response.get_data(as_text=True))
                model.assert_called_once_with(payload['query'], last_response=(payload.get('last_response', '') if app_module._env_bool('ATLAS_USE_LAST_RESPONSE', False) and isinstance(payload.get('last_response', ''), str) and len(payload.get('last_response', '')) <= 16000 else ''))
            else:
                self.assertEqual(response.get_json()['error'], error)
                model.assert_not_called()

    def test_synthetic_scenarios(self):
        for name, (words, _) in SCENARIOS.items():
            text = make_scenario(name)
            m = metrics(text)
            self.assertEqual(m['words'], words)
            body_size = len(json.dumps({'query': text}, ensure_ascii=True).encode())
            status = 413 if body_size > 1048576 else 400 if len(text) > 16000 else 200
            error = 'Request is too large.' if status == 413 else 'Question must be 16,000 characters or fewer.'
            for route in ROUTES:
                with self.subTest(scenario=name, route=route, metrics=m, body_bytes=body_size):
                    self.check_request(route, {'query': text}, status, error)

    def test_query_and_previous_response_boundaries(self):
        for route in ROUTES:
            for size in (15999, 16000, 16001):
                with self.subTest(route=route, query=size):
                    self.check_request(route, {'query': 'x' * size}, 200 if size <= 16000 else 400,
                                       'Question must be 16,000 characters or fewer.')
            for size in (15999, 16000, 16001):
                with self.subTest(route=route, previous=size), patch.dict('os.environ', {'ATLAS_USE_LAST_RESPONSE': 'true'}):
                    self.check_request(route, {'query': 'Hi', 'last_response': 'y' * size}, 200)

    def test_request_byte_boundaries(self):
        prefix = b'{"query":"Hi","padding":"'
        suffix = b'"}'
        for route in ROUTES:
            for size in (1048575, 1048576, 1048577):
                body = prefix + b'x' * (size - len(prefix) - len(suffix)) + suffix
                app_module.limiter.reset()
                with self.subTest(route=route, bytes=size), patch('app.ask_atlas', return_value='Answer') as model:
                    response = self.client.post(route, data=body, content_type='application/json', buffered=True)
                    self.addCleanup(response.close)
                    self.assertEqual(response.status_code, 200 if size <= 1048576 else 413)
                    if size <= 1048576:
                        model.assert_called_once_with('Hi', last_response='')
                    else:
                        self.assertEqual(response.get_json()['error'], 'Request is too large.')
                        model.assert_not_called()

    def test_formatting_and_unicode_reach_model_intact(self):
        samples = ['  Hola, ¿puedo transferir créditos? 你好 🎓 & < >\n\nSecond paragraph.  ',
                   '# Outline\n- first\n- second\n\n<p>pasted HTML</p>', 'x' * 4000,
                   '🙂' * 4000]
        for route in ROUTES:
            for text in samples:
                with self.subTest(route=route, metrics=metrics(text)):
                    self.check_request(route, {'query': text}, 200)

    def test_empty_and_malformed(self):
        for route in ROUTES:
            for text in ('', ' \n\t'):
                self.check_request(route, {'query': text}, 400, 'No query provided')
            for body in ('{', 'null', '[]', '"text"'):
                app_module.limiter.reset()
                with self.subTest(route=route, body=body), patch('app.ask_atlas') as model:
                    response = self.client.post(route, data=body, content_type='application/json')
                    self.addCleanup(response.close)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.get_json()['error'], 'A JSON object is required.')
                    model.assert_not_called()

    def test_long_conversation_only_passes_supplied_previous_answer(self):
        for route in ROUTES:
            for turn in range(15):
                self.check_request(route, {'query': f'Turn {turn}: What should I ask?',
                                          'last_response': f'Answer {turn - 1}'}, 200)

    def test_configured_limit_and_escaped_unicode_combination(self):
        with patch.dict(app_module.app.config, CHAT_MAX_QUESTION_CHARS=32000), patch.dict('os.environ', {'ATLAS_USE_LAST_RESPONSE': 'true'}):
            response = self.client.get('/api/input-config')
            self.assertEqual(response.get_json()['max_question_chars'], 32000)
            for route in ROUTES:
                self.check_request(route, {'query': '\U0001f642' * 32000, 'last_response': '\U0001f642' * 16000}, 200)
                self.check_request(route, {'query': '\U0001f642' * 32001}, 400, 'Question must be 32,000 characters or fewer.')

    def test_previous_response_disabled_and_omission_is_signaled(self):
        for route in ROUTES:
            with patch.dict('os.environ', {'ATLAS_USE_LAST_RESPONSE': 'false'}):
                self.check_request(route, {'query': 'Hi', 'last_response': []}, 200)
            with patch.dict('os.environ', {'ATLAS_USE_LAST_RESPONSE': 'true'}), patch('app.ask_atlas', return_value='Answer') as model:
                app_module.limiter.reset()
                response = self.client.post(route, json={'query': 'Hi', 'last_response': 'x' * 16001}, buffered=True)
                self.addCleanup(response.close)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['X-BLS-Context-Omitted'], 'previous-response-too-long')
                model.assert_called_once_with('Hi', last_response='')
                self.check_request(route, {'query': 'Hi', 'last_response': []}, 400, 'Invalid previous response.')

    def test_model_payload_preserves_whitespace_and_has_no_user_history(self):
        text = '  First paragraph.\n\nSecond paragraph.  '
        for enabled in (False, True):
            settings = AtlasSettings(api_key='', use_last_response=enabled)
            payload = build_payload(text, settings, last_response='  Earlier answer  ')
            self.assertEqual(payload['messages'][-1], {'role': 'user', 'content': text})
            self.assertEqual([m['role'] for m in payload['messages']],
                             ['system', 'assistant', 'user'] if enabled else ['system', 'user'])
            if enabled:
                self.assertEqual(payload['messages'][1]['content'], 'Earlier answer')

if __name__ == '__main__':
    unittest.main()

