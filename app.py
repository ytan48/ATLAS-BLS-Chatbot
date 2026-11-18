"""Flask web service for the BLS Virtual Advisor."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from flask import Flask, Response, g, jsonify, request, send_from_directory, stream_with_context
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException

from atlas_chat import AtlasAPIError, AtlasConfigurationError, AtlasSettings, ask_atlas, _env_bool


load_dotenv()

app = Flask(__name__)
# Even JSON-escaped supplementary Unicode in both fields fits at these bounds.
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
try:
    app.config["CHAT_MAX_QUESTION_CHARS"] = int(os.getenv("CHAT_MAX_QUESTION_CHARS", "16000"))
    if not 1 <= app.config["CHAT_MAX_QUESTION_CHARS"] <= 32000:
        raise ValueError
except ValueError as exc:
    raise RuntimeError("CHAT_MAX_QUESTION_CHARS must be an integer from 1 to 32000.") from exc
MAX_PREVIOUS_RESPONSE_CHARS = 16000
allowed_origins = [
    origin.strip()
    for origin in os.getenv("CHAT_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if allowed_origins:
    CORS(
        app, resources={r"/api/*": {"origins": allowed_origins}},
        methods=["GET", "POST"], allow_headers=["Content-Type"],
    )
limiter = Limiter(
    get_remote_address, app=app,
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    headers_enabled=True,
)
chat_limit = limiter.shared_limit(
    os.getenv("CHAT_RATE_LIMIT", "10 per minute"), scope="chat"
)
logger = logging.getLogger(__name__)


@app.before_request
def validate_chat_request():
    chat_routes = {"/api/ask", "/api/chat", "/api/stream"}
    if request.method != "POST" or request.path not in chat_routes:
        return None
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="A JSON object is required."), 400
    query = data.get("query", "")
    if not isinstance(query, str) or not query.strip():
        return jsonify(error="No query provided"), 400
    limit = app.config["CHAT_MAX_QUESTION_CHARS"]
    if len(query) > limit:
        return jsonify(error=f"Question must be {limit:,} characters or fewer.", code="question_too_long"), 400
    try:
        if _env_bool("ATLAS_USE_LAST_RESPONSE", False):
            previous = data.get("last_response", "")
            if not isinstance(previous, str):
                return jsonify(error="Invalid previous response."), 400
            if len(previous) > MAX_PREVIOUS_RESPONSE_CHARS:
                g.previous_context_omitted = True
    except AtlasConfigurationError as exc:
        return _json_error(exc)


@app.errorhandler(413)
def request_too_large(exc):
    return jsonify(error="Request is too large."), 413


@app.errorhandler(429)
def too_many_requests(exc):
    response = jsonify(error="Too many requests. Please wait before trying again.")
    response.status_code = 429
    return response


@app.after_request
def security_headers(response):
    if getattr(g, "previous_context_omitted", False):
        response.headers["X-BLS-Context-Omitted"] = "previous-response-too-long"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def _request_data() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _answer_request(data: dict[str, Any]) -> str:
    query = data.get("query", "")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("No query provided")

    last_response = data.get("last_response", "") if _env_bool("ATLAS_USE_LAST_RESPONSE", False) else ""
    if not isinstance(last_response, str) or len(last_response) > MAX_PREVIOUS_RESPONSE_CHARS:
        last_response = ""
    return ask_atlas(query, last_response=last_response)


def _json_error(exc: Exception):
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ValueError) and str(exc) == "No query provided":
        return jsonify({"error": str(exc)}), 400
    if isinstance(exc, AtlasConfigurationError):
        logger.error("ATLAS configuration error: %s", exc)
        return jsonify({"error": "The advisor service is temporarily unavailable."}), 503
    if isinstance(exc, AtlasAPIError):
        logger.error("ATLAS API error: %s", exc)
        return jsonify({"error": "Unable to reach the advisor service. Please try again."}), 502
    logger.exception("Unexpected BLS chatbot error")
    return jsonify({"error": "Unable to generate a response."}), 500


@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/widget")
def widget():
    return send_from_directory("frontend", "widget.html")


@app.route("/assets/<path:filename>")
def frontend_asset(filename):
    return send_from_directory("frontend/vendor", filename)


@app.route("/embed.js")
def embed_js():
    return (
        send_from_directory("frontend", "embed.js"),
        200,
        {"Content-Type": "application/javascript"},
    )


@app.route("/api/ask", methods=["POST"])
@chat_limit
def ask_chatbot():
    """Compatibility endpoint used by the full-page chatbot fallback."""

    try:
        return jsonify({"answer": _answer_request(_request_data())})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/chat", methods=["POST"])
@chat_limit
def chat_widget_api():
    """Compatibility endpoint used by the embeddable widget fallback."""

    try:
        answer = _answer_request(_request_data())
        return jsonify({"answer": answer, "pipeline": "atlas_single_completion"})
    except Exception as exc:
        return _json_error(exc)


def _sse_event(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.route("/api/stream", methods=["POST"])
@chat_limit
def stream_chat():
    """Keep the existing SSE contract while using one ATLAS completion call."""

    data = _request_data()
    query = data.get("query", "")
    if not isinstance(query, str) or not query.strip():
        return jsonify({"error": "No query provided"}), 400

    def generate():
        yield _sse_event(
            {
                "type": "agent_status",
                "agent": "A",
                "message": "Loading the BLS instructions and knowledge base…",
            }
        )
        yield _sse_event(
            {
                "type": "agent_status",
                "agent": "B",
                "message": "Generating your answer with the ATLAS model…",
            }
        )

        try:
            answer = _answer_request(data)
        except Exception as exc:
            if isinstance(exc, (AtlasConfigurationError, AtlasAPIError)):
                logger.error("Streaming BLS chatbot request failed: %s", exc)
                message = "The advisor service is temporarily unavailable. Please try again."
            else:
                logger.exception("Streaming BLS chatbot request failed")
                message = "Unable to generate a response. Please try again."
            yield _sse_event({"type": "error", "message": message})
            yield _sse_event({"type": "done"})
            return

        yield _sse_event({"type": "answer", "content": answer})
        yield _sse_event({"type": "done"})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/input-config", methods=["GET"])
def input_config():
    try:
        return jsonify(max_question_chars=app.config["CHAT_MAX_QUESTION_CHARS"],
                       max_previous_response_chars=MAX_PREVIOUS_RESPONSE_CHARS,
                       use_last_response=_env_bool("ATLAS_USE_LAST_RESPONSE", False))
    except AtlasConfigurationError as exc:
        return _json_error(exc)


@app.route("/api/config", methods=["GET"])
def public_config():
    """Expose non-secret runtime settings for deployment diagnostics."""

    try:
        settings = AtlasSettings.from_env()
    except AtlasConfigurationError as exc:
        return _json_error(exc)
    return jsonify(
        {
            "provider": "ATLAS LLM Server",
            "model": settings.model,
            "temperature": settings.temperature,
            "reasoning_effort": settings.reasoning_effort,
            "use_last_response": settings.use_last_response,
            "instructions_file": settings.instructions_file.name,
            "knowledge_base_file": settings.knowledge_base_file.name,
            "api_key_configured": bool(settings.api_key),
        }
    )


if __name__ == "__main__":
    app.run(debug=False, port=5001)
