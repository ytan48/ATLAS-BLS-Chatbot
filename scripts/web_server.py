#!/usr/bin/env python3
"""Local dev server for the BLS Virtual Advisor frontend + chat API.

Serves files from the `frontend/` folder and exposes `/api/ask` and
`/api/chat` endpoints which proxy to the `ask()` function in
`scripts/bls_chat.py`.

Run: python3 scripts/web_server.py
"""
from pathlib import Path
import os
import logging

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

def get_ask_callable():
    """Dynamically import `ask` so import issues surface in server logs.

    Importing at request-time helps avoid silent failures when the module
    import path differs between environments.
    """
    try:
        from scripts.bls_chat import ask as ask_fn
        return ask_fn
    except Exception:
        logging.exception('Failed to import ask from scripts.bls_chat')
        raise

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path='')
CORS(app)


@app.route('/')
def index():
    return send_from_directory(str(FRONTEND_DIR), 'index.html')


@app.route('/widget')
def widget():
    return send_from_directory(str(FRONTEND_DIR), 'widget.html')


@app.route('/assets/<path:filename>')
def frontend_asset(filename: str):
    return send_from_directory(FRONTEND_DIR / 'vendor', filename)


@app.route('/embed.js')
def embed_js():
    return send_from_directory(str(FRONTEND_DIR), 'embed.js')


@app.route('/api/ask', methods=['POST'])
def api_ask():
    data = request.get_json(silent=True) or {}
    query = data.get('query') or data.get('message') or ''
    if not query:
        return jsonify({'error': 'no query provided'}), 400
    try:
        ask_fn = get_ask_callable()
        answer = ask_fn(query)
        return jsonify({'answer': answer})
    except Exception as e:
        logging.exception('ask() failed')
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def api_chat():
    return api_ask()


@app.route('/static/<path:filename>')
def static_files(filename: str):
    return send_from_directory(str(FRONTEND_DIR), filename)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5000'))
    host = os.environ.get('HOST', '127.0.0.1')
    logging.basicConfig(level=logging.INFO)
    logging.info(f"Serving frontend from {FRONTEND_DIR} on http://{host}:{port}")
    app.run(host=host, port=port)
