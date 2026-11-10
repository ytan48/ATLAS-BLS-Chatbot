"""ATLAS LLM client adapted from UIUCATLAS/chat_illinois_cli.

The reference CLI builds one system prompt by concatenating an instructions
file and a Markdown knowledge base, then sends a single OpenAI-compatible chat
completion request to the ATLAS inference server.  This module keeps that
request shape while exposing it to the Flask application.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_API_URL = "https://sequitor01.atlas.illinois.edu/v1/chat/completions"
DEFAULT_MODEL = "qwen3.8-27b"
ALLOWED_REASONING_EFFORTS = {"low", "medium", "xhigh"}


class AtlasConfigurationError(ValueError):
    """Raised when the local ATLAS configuration is incomplete or invalid."""


class AtlasAPIError(RuntimeError):
    """Raised when the ATLAS server rejects or returns an invalid response."""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise AtlasConfigurationError(
        f"{name} must be one of true/false, yes/no, on/off, or 1/0."
    )


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise AtlasConfigurationError(f"{name} must be a number.") from exc


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise AtlasConfigurationError(f"{name} must be an integer.") from exc


def _resolve_config_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


@dataclass(frozen=True)
class AtlasSettings:
    """Model and prompt settings corresponding to ``vars.py.example``."""

    api_key: str
    api_url: str = DEFAULT_API_URL
    model: str = DEFAULT_MODEL
    temperature: float = 0.1
    reasoning_effort: str = "low"
    use_last_response: bool = False
    instructions_file: Path = PROJECT_ROOT / "config" / "instructions.txt"
    knowledge_base_file: Path = PROJECT_ROOT / "config" / "knowledgebase.md"
    timeout_seconds: int = 60

    @classmethod
    def from_env(cls) -> "AtlasSettings":
        settings = cls(
            api_key=os.getenv("ATLAS_API_KEY", "").strip(),
            api_url=os.getenv("ATLAS_API_URL", DEFAULT_API_URL).strip(),
            model=os.getenv("ATLAS_MODEL", DEFAULT_MODEL).strip(),
            temperature=_env_float("ATLAS_TEMPERATURE", 0.1),
            reasoning_effort=os.getenv("ATLAS_REASONING_EFFORT", "low")
            .strip()
            .lower(),
            use_last_response=_env_bool("ATLAS_USE_LAST_RESPONSE", False),
            instructions_file=_resolve_config_path(
                os.getenv("ATLAS_INSTRUCTIONS_FILE", "config/instructions.txt")
            ),
            knowledge_base_file=_resolve_config_path(
                os.getenv("ATLAS_KNOWLEDGE_BASE_FILE", "config/knowledgebase.md")
            ),
            timeout_seconds=_env_int("ATLAS_TIMEOUT_SECONDS", 60),
        )
        settings.validate(require_api_key=False)
        return settings

    def validate(self, *, require_api_key: bool = True) -> None:
        if require_api_key and not self.api_key:
            raise AtlasConfigurationError(
                "ATLAS_API_KEY is not set. Add the PEAR-provided key to .env."
            )
        if not self.api_url:
            raise AtlasConfigurationError("ATLAS_API_URL cannot be empty.")
        if not self.model:
            raise AtlasConfigurationError("ATLAS_MODEL cannot be empty.")
        if not 0.0 <= self.temperature <= 2.0:
            raise AtlasConfigurationError(
                "ATLAS_TEMPERATURE must be between 0.0 and 2.0."
            )
        if self.reasoning_effort not in ALLOWED_REASONING_EFFORTS:
            allowed = ", ".join(sorted(ALLOWED_REASONING_EFFORTS))
            raise AtlasConfigurationError(
                f"ATLAS_REASONING_EFFORT must be one of: {allowed}."
            )
        if self.timeout_seconds <= 0:
            raise AtlasConfigurationError("ATLAS_TIMEOUT_SECONDS must be positive.")


def load_system_prompt(settings: AtlasSettings) -> str:
    """Load instructions + knowledge base exactly like the reference CLI."""

    settings.validate(require_api_key=False)
    try:
        instructions = settings.instructions_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise AtlasConfigurationError(
            f"Unable to read instructions file: {settings.instructions_file}"
        ) from exc
    try:
        knowledge_base = settings.knowledge_base_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise AtlasConfigurationError(
            f"Unable to read knowledge base file: {settings.knowledge_base_file}"
        ) from exc
    return instructions + "\n" + knowledge_base


def build_payload(
    question: str,
    settings: AtlasSettings,
    *,
    last_response: str = "",
) -> dict[str, Any]:
    """Build the OpenAI-compatible request used by ``chat.py``."""

    messages: list[dict[str, str]] = [
        {"role": "system", "content": load_system_prompt(settings)}
    ]
    if settings.use_last_response and last_response.strip():
        messages.append({"role": "assistant", "content": last_response.strip()})
    messages.append({"role": "user", "content": question.strip()})
    return {
        "model": settings.model,
        "messages": messages,
        "temperature": settings.temperature,
        "reasoning_effort": settings.reasoning_effort,
    }


def extract_answer(response: Any) -> str:
    """Return the assistant content from an OpenAI-compatible response."""

    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AtlasAPIError("ATLAS returned an unexpected response format.") from exc
    if not isinstance(content, str) or not content.strip():
        raise AtlasAPIError("ATLAS returned an empty answer.")
    return content.replace("\\n", "\n").strip()


def ask_atlas(
    question: str,
    *,
    last_response: str = "",
    settings: AtlasSettings | None = None,
) -> str:
    """Send one BLS question to the ATLAS LLM server."""

    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty.")

    current_settings = settings or AtlasSettings.from_env()
    current_settings.validate(require_api_key=True)
    payload = build_payload(
        question,
        current_settings,
        last_response=last_response,
    )
    request = urllib.request.Request(
        current_settings.api_url,
        json.dumps(payload).encode("utf-8"),
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {current_settings.api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=current_settings.timeout_seconds
        ) as response:
            body = response.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="ignore")
        except OSError:
            detail = ""
        suffix = f": {detail}" if detail else ""
        raise AtlasAPIError(f"ATLAS request failed with HTTP {exc.code}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise AtlasAPIError(f"Unable to reach the ATLAS server: {exc.reason}") from exc
    except TimeoutError as exc:
        raise AtlasAPIError("The ATLAS request timed out.") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AtlasAPIError("ATLAS returned invalid JSON.") from exc
    return extract_answer(parsed)
