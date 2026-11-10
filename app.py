"""Flask web service for the BLS Virtual Advisor."""

from __future__ import annotations

import json
import logging
from typing import Any

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context
from flask_cors import CORS

from atlas_chat import AtlasAPIError, AtlasConfigurationError, AtlasSettings, ask_atlas


load_dotenv()

app = Flask(__name__)
CORS(app)
logger = logging.getLogger(__name__)


def _request_data() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _answer_request(data: dict[str, Any]) -> str:
    query = data.get("query", "")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("No query provided")

    last_response = data.get("last_response", "")
    if not isinstance(last_response, str):
        last_response = ""
    return ask_atlas(query, last_response=last_response)


def _json_error(exc: Exception):
    if isinstance(exc, ValueError) and str(exc) == "No query provided":
        return jsonify({"error": str(exc)}), 400
    if isinstance(exc, AtlasConfigurationError):
        logger.error("ATLAS configuration error: %s", exc)
        return jsonify({"error": str(exc)}), 503
    if isinstance(exc, AtlasAPIError):
        logger.error("ATLAS API error: %s", exc)
        return jsonify({"error": str(exc)}), 502
    logger.exception("Unexpected BLS chatbot error")
    return jsonify({"error": "Unable to generate a response."}), 500


@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/widget")
def widget():
    return send_from_directory("frontend", "widget.html")


@app.route("/embed.js")
def embed_js():
    return (
        send_from_directory("frontend", "embed.js"),
        200,
        {"Content-Type": "application/javascript"},
    )


@app.route("/api/ask", methods=["POST"])
def ask_chatbot():
    """Compatibility endpoint used by the full-page chatbot fallback."""

    try:
        return jsonify({"answer": _answer_request(_request_data())})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/chat", methods=["POST"])
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
                message = str(exc)
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
    app.run(debug=True, port=5001)
