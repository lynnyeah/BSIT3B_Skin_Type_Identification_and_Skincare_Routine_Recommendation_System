"""Server-side Gemini helpers for the SkinSync assistant.

The browser never receives the Gemini API key. It receives a short-lived,
single-use ephemeral token for the Live API and talks to Django for text-mode
messages and final assessment extraction.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from django.conf import settings

from .prompts import (
    ANALYSIS_SYSTEM_PROMPT,
    ASSESSMENT_SCHEMA,
    LIVE_SYSTEM_PROMPT,
    TEXT_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_MESSAGES = 200
MAX_MESSAGE_CHARS = 4000
MAX_ANALYSIS_TRANSCRIPT_CHARS = 24000

# Extra capacity for thinking-class models, where some output tokens go to
# reasoning before the visible reply is written.
CHAT_MAX_OUTPUT_TOKENS = 2400
ASSESSMENT_MAX_OUTPUT_TOKENS = 4000

# Modest, widely available models used when the primary text model is
# overloaded (HTTP 503) or otherwise cannot serve the request.
DEFAULT_TEXT_FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-2.5-flash-lite"]

SKIN_TYPE_LABELS = {
    "oily": "Oily",
    "dry": "Dry",
    "normal": "Normal",
    "combination": "Combination",
    "uncertain": "Uncertain",
}
SENSITIVITY_LABELS = {
    "low": "Low",
    "moderate": "Moderate",
    "high": "High",
    "unknown": "Unknown",
}

DISCLAIMER = "This is an AI-generated estimate, not a medical diagnosis."

DEFAULT_MORNING = [
    "Gentle cleanser",
    "Lightweight moisturizer suited to your skin",
    "Broad-spectrum sunscreen SPF 30 or higher",
]
DEFAULT_EVENING = [
    "Gentle cleanser",
    "Moisturizer",
    "Optional gentle treatment two to three nights per week if tolerated",
]
DEFAULT_INGREDIENTS = [
    "Ceramides",
    "Glycerin",
    "Hyaluronic acid",
    "Niacinamide (if tolerated)",
]
DEFAULT_PRECAUTIONS = [
    "Patch test new products on a small area before using them on your whole face.",
    "Introduce one new active ingredient at a time and start slowly.",
    "Use sunscreen every morning and reapply when outdoors.",
    "Stop a product if it causes lasting irritation, and consult a dermatologist for persistent or serious skin concerns.",
]
DEFAULT_FOLLOW_UPS = [
    "How does your skin feel a few hours after cleansing?",
    "Do you notice shine mainly on your T-zone or all over your face?",
    "How often do you get flaking, tightness, or irritation?",
    "How often do you experience breakouts?",
]


class GeminiError(Exception):
    """A safe, user-facing Gemini integration error."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.public_message = message
        self.retryable = retryable


class GeminiConfigurationError(GeminiError):
    def __init__(self, message: str):
        super().__init__(message, retryable=False)


def api_key() -> str:
    key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not key:
        raise GeminiConfigurationError(
            "Gemini is not configured yet. Add GEMINI_API_KEY to the project's "
            ".env file, then restart the Django server."
        )
    return key


def live_model() -> str:
    return (getattr(settings, "GEMINI_LIVE_MODEL", "") or "gemini-3.8-live").strip()


def text_model() -> str:
    return (getattr(settings, "GEMINI_TEXT_MODEL", "") or "gemini-3.8-flash").strip()


def text_model_chain() -> list[str]:
    """Primary text model plus any fallbacks configured for overloaded days."""
    chain = [text_model()]
    raw = getattr(settings, "GEMINI_TEXT_FALLBACK_MODELS", None)
    if raw is None:
        candidates = DEFAULT_TEXT_FALLBACK_MODELS
    elif isinstance(raw, (list, tuple)):
        candidates = [str(name) for name in raw]
    else:
        candidates = str(raw).split(",")
    for name in candidates:
        candidate = name.strip()
        if candidate and candidate not in chain:
            chain.append(candidate)
    return chain


def live_voice() -> str:
    return (getattr(settings, "GEMINI_LIVE_VOICE", "") or "Aoede").strip()


def max_session_seconds() -> int:
    try:
        value = int(getattr(settings, "GEMINI_ASSISTANT_MAX_SECONDS", 840))
    except (TypeError, ValueError):
        value = 840
    return max(120, min(value, 890))


def _api_base() -> str:
    return (
        getattr(settings, "GEMINI_API_BASE", "")
        or "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")


def _live_ws_url() -> str:
    return (
        getattr(settings, "GEMINI_LIVE_WS_URL", "")
        or (
            "wss://generativelanguage.googleapis.com/ws/"
            "google.ai.generativelanguage.v1beta.GenerativeService."
            "BidiGenerateContentConstrained"
        )
    )


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _response_error(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else {}
    if isinstance(error, dict):
        detail = str(error.get("message") or "").strip()
    else:
        detail = str(error or "").strip()
    if detail:
        return detail[:400]
    return (response.text or "").strip()[:400]


def _friendly_http_error(status_code: int, detail: str, model: str) -> GeminiError:
    logger.warning("Gemini API error %s for model %s: %s", status_code, model, detail)
    if status_code in (401, 403):
        return GeminiError(
            "The Gemini API key was rejected. Check that GEMINI_API_KEY is valid "
            "and that the key has access to the Gemini API.",
            retryable=False,
        )
    if status_code == 404:
        return GeminiError(
            f"The configured Gemini model ({model}) was not found for this API "
            "key. Update GEMINI_LIVE_MODEL or GEMINI_TEXT_MODEL in .env.",
            retryable=False,
        )
    if status_code == 429:
        return GeminiError(
            "Gemini is temporarily rate-limited. Please wait a moment and try again."
        )
    if status_code >= 500:
        return GeminiError(
            "Gemini is temporarily unavailable. Please try again shortly."
        )
    return GeminiError(
        "Gemini could not process the request. Please try again, or check the "
        "server log for details."
    )


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _post(
    url: str, payload: dict[str, Any], *, timeout: int = 30, attempts: int = 3
) -> dict[str, Any]:
    headers = {
        "x-goog-api-key": api_key(),
        "Content-Type": "application/json",
    }
    connection_error: GeminiError | None = None

    for attempt in range(max(1, attempts)):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            logger.warning(
                "Could not reach Gemini (attempt %s): %s", attempt + 1, exc
            )
            connection_error = GeminiError(
                "Could not reach Gemini. Check the server's internet connection and try again."
            )
            if attempt + 1 < max(1, attempts):
                time.sleep(1.5 * (attempt + 1))
            continue

        if response.status_code in RETRYABLE_STATUS_CODES and attempt + 1 < max(1, attempts):
            wait = 1.5 * (attempt + 1)
            logger.warning(
                "Gemini returned %s (attempt %s). Retrying in %.1fs.",
                response.status_code,
                attempt + 1,
                wait,
            )
            time.sleep(wait)
            continue

        if response.status_code >= 400:
            model = str(payload.get("model") or "gemini")
            raise _friendly_http_error(
                response.status_code, _response_error(response), model
            )

        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("Gemini returned non-JSON content: %s", response.text[:300])
            raise GeminiError(
                "Gemini returned an unexpected response. Please try again."
            ) from exc

        if not isinstance(data, dict):
            raise GeminiError("Gemini returned an unexpected response. Please try again.")
        return data

    raise connection_error or GeminiError(
        "Could not reach Gemini. Check the server's internet connection and try again."
    )


def _post_text(payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    """Call generateContent on the primary text model, then on fallbacks.

    The fallback chain keeps text chat and assessment working when the primary
    model is temporarily overloaded (a 503 "high demand" response) or is not
    available to this API key at all.
    """
    chain = text_model_chain()
    last_error: GeminiError | None = None
    for model in chain:
        try:
            return _post(
                f"{_api_base()}/models/{model}:generateContent",
                payload,
                timeout=timeout,
            )
        except GeminiError as exc:
            if isinstance(exc, GeminiConfigurationError):
                raise
            last_error = exc
            logger.warning("Gemini model %s could not serve the request: %s", model, exc)
    if last_error:
        raise last_error
    raise GeminiError("Gemini could not process the request. Please try again.")


def create_live_token(*, user_context: str = "") -> dict[str, Any]:
    """Create a short-lived, single-use token for the browser Live session.

    ``user_context`` is appended to the system prompt so the AI answers with
    the signed-in user's saved skin type, concerns, and routine in mind.
    """
    model = live_model()
    system_instruction = (
        f"{LIVE_SYSTEM_PROMPT}\n\n{user_context.strip()}" if user_context.strip()
        else LIVE_SYSTEM_PROMPT
    )
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "uses": 1,
        "expireTime": _iso_utc(now + timedelta(minutes=30)),
        "newSessionExpireTime": _iso_utc(now + timedelta(minutes=2)),
    }
    if getattr(settings, "GEMINI_LIVE_LOCK_CONSTRAINTS", True):
        # The token pins the model, output modality, voice, and system prompt.
        # The browser sends the same setup message when it opens the socket.
        payload["bidiGenerateContentSetup"] = {
            "model": f"models/{model}",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": live_voice()}
                    }
                },
            },
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
        }

    data = _post(f"{_api_base()}/auth_tokens", payload, timeout=25)
    token = data.get("name")
    if not token or not isinstance(token, str):
        logger.warning("Gemini auth token response did not contain a name: %s", data)
        raise GeminiError(
            "Gemini did not return a usable voice-session token. Please try again."
        )

    return {
        "token": token,
        "ws_url": _live_ws_url(),
        "model": model,
        "voice": live_voice(),
        "system_instruction": system_instruction,
        "max_seconds": max_session_seconds(),
        "expires_at": _iso_utc(now + timedelta(minutes=30)),
    }


def _merge_turns(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for item in messages[-60:]:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        role = "user" if item.get("role") == "user" else "model"
        if turns and turns[-1]["role"] == role:
            existing = turns[-1]["parts"][0]["text"]
            turns[-1]["parts"][0]["text"] = f"{existing}\n\n{text}"[:12000]
        else:
            turns.append({"role": role, "parts": [{"text": text[:12000]}]})

    # Keep the prompt inside a reasonable size without dropping recent turns.
    total = 0
    kept: list[dict[str, Any]] = []
    for turn in reversed(turns):
        length = len(turn["parts"][0]["text"])
        if total + length > 30000 and kept:
            break
        kept.append(turn)
        total += length
    kept.reverse()
    return kept


def _extract_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        feedback = data.get("promptFeedback") or {}
        reason = feedback.get("blockReason") if isinstance(feedback, dict) else None
        if reason:
            raise GeminiError(
                "Gemini could not respond to that message because of a safety "
                "filter. Try rephrasing your answer."
            )
        raise GeminiError("Gemini returned an empty response. Please try again.")

    candidate = candidates[0] or {}
    content = candidate.get("content") or {}
    parts = content.get("parts") or []
    chunks = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get("thought"):
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())

    if not chunks:
        finish_reason = str(candidate.get("finishReason") or "")
        if finish_reason in {"SAFETY", "RECITATION", "PROHIBITED_CONTENT"}:
            raise GeminiError(
                "Gemini could not respond to that message because of a safety "
                "filter. Try rephrasing your answer."
            )
        raise GeminiError("Gemini returned an empty response. Please try again.")

    return "\n".join(chunks)


def chat_reply(
    messages: list[dict[str, Any]],
    *,
    mode: str = "text",
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Send the conversation to Gemini and return the assistant's next turn.

    ``system_prompt`` lets callers personalise the base prompt (for example
    with the signed-in user's saved skin profile) without rebuilding the
    request plumbing here.
    """
    turns = _merge_turns(messages)
    if not turns:
        raise GeminiError("There is no conversation to send yet.")

    system_prompt = system_prompt or (
        TEXT_SYSTEM_PROMPT if mode == "text" else LIVE_SYSTEM_PROMPT
    )
    model = text_model()
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": turns,
        "generationConfig": {
            "temperature": 0.65,
            "topP": 0.95,
            "maxOutputTokens": CHAT_MAX_OUTPUT_TOKENS,
        },
    }

    data = _post_text(payload, timeout=90)
    raw_text = _extract_text(data)
    ready = bool(re.search(r"\[\[\s*ASSESSMENT_READY\s*\]\]", raw_text, re.IGNORECASE))
    reply = re.sub(
        r"\[\[\s*ASSESSMENT_READY\s*\]\]", "", raw_text, flags=re.IGNORECASE
    ).strip()

    if not reply:
        raise GeminiError("Gemini returned an empty message. Please try again.")

    return {
        "reply": reply,
        "assessment_ready": ready,
        "model": model,
    }


def transcript_to_text(transcript: list[dict[str, Any]]) -> str:
    lines = []
    for item in transcript[-MAX_TRANSCRIPT_MESSAGES:]:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        role = "User" if item.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {text}")
    return "\n\n".join(lines)[-MAX_ANALYSIS_TRANSCRIPT_CHARS:]


def _clean_text(value: Any, *, limit: int = 1500, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit] if text else default


def _clean_list(value: Any, *, limit: int = 8, item_limit: int = 300) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        pieces = re.split(r"[\n;]+", value)
    elif isinstance(value, (list, tuple)):
        pieces = list(value)
    else:
        pieces = [value]

    cleaned: list[str] = []
    for item in pieces:
        text = _clean_text(item, limit=item_limit)
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _clean_enum(value: Any, allowed: dict[str, str], default: str) -> str:
    candidate = _clean_text(value, limit=40).lower().replace(" ", "_")
    if candidate in allowed:
        return candidate
    for key, label in allowed.items():
        if label.lower() == candidate:
            return key
    return default


def _normalise_routine(value: Any) -> dict[str, list[str]]:
    if isinstance(value, dict):
        morning = _clean_list(value.get("morning"), limit=8, item_limit=220)
        evening = _clean_list(value.get("evening"), limit=8, item_limit=220)
    else:
        morning = []
        evening = []
    return {
        "morning": morning or list(DEFAULT_MORNING),
        "evening": evening or list(DEFAULT_EVENING),
    }


def normalize_assessment(
    data: dict[str, Any],
    *,
    transcript: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate and normalise Gemini's structured assessment."""
    if not isinstance(data, dict):
        data = {}

    transcript = transcript or []
    user_turns = sum(
        1
        for item in transcript
        if item.get("role") == "user" and len(str(item.get("text") or "").strip()) >= 3
    )
    enough_turns = user_turns >= 2

    sufficient = bool(data.get("information_sufficient")) and enough_turns
    primary = _clean_enum(data.get("primary_skin_type"), SKIN_TYPE_LABELS, "uncertain")
    sensitivity = _clean_enum(
        data.get("sensitivity_level"), SENSITIVITY_LABELS, "unknown"
    )

    if not sufficient:
        primary = "uncertain"

    summary = _clean_text(data.get("summary"), limit=1600)
    if not summary:
        summary = (
            "There was not enough consistent information in this conversation "
            "to estimate a skin type."
            if not sufficient
            else "The conversation suggests a possible skin type, but this is "
            "only an AI-generated estimate."
        )
    if "diagnos" not in summary.lower() and "ai-generated estimate" not in summary.lower():
        summary = f"{summary} {DISCLAIMER}".strip()

    observations = _clean_list(data.get("observations"), limit=10, item_limit=320)
    if not observations:
        observations = (
            [
                "The conversation did not include enough specific details about "
                "oiliness, dryness, flaking, shine, sensitivity, or breakouts."
            ]
            if not sufficient
            else ["The user's answers were recorded in the conversation transcript."]
        )

    follow_ups = _clean_list(
        data.get("follow_up_questions"), limit=6, item_limit=240
    )
    if not sufficient and not follow_ups:
        follow_ups = list(DEFAULT_FOLLOW_UPS)

    ingredients = _clean_list(data.get("ingredients"), limit=10, item_limit=120)
    precautions = _clean_list(data.get("precautions"), limit=8, item_limit=320)

    return {
        "information_sufficient": sufficient,
        "primary_skin_type": primary,
        "primary_skin_type_label": SKIN_TYPE_LABELS[primary],
        "sensitivity_level": sensitivity,
        "sensitivity_level_label": SENSITIVITY_LABELS[sensitivity],
        "summary": summary,
        "observations": observations,
        "routine": _normalise_routine(data.get("routine")),
        "ingredients": ingredients or list(DEFAULT_INGREDIENTS),
        "precautions": precautions or list(DEFAULT_PRECAUTIONS),
        "follow_up_questions": follow_ups,
        "disclaimer": DISCLAIMER,
        "user_turns": user_turns,
    }


def _parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except ValueError as exc:
        raise GeminiError(
            "Gemini returned an assessment in an unexpected format. Please try again."
        ) from exc
    if not isinstance(parsed, dict):
        raise GeminiError(
            "Gemini returned an assessment in an unexpected format. Please try again."
        )
    return parsed


def analyze_transcript(transcript: list[dict[str, Any]]) -> dict[str, Any]:
    """Ask Gemini to turn the conversation into a structured assessment."""
    transcript_text = transcript_to_text(transcript)
    if not transcript_text.strip():
        raise GeminiError(
            "There is not enough conversation to assess yet. Answer a few questions first.",
            retryable=False,
        )

    model = text_model()
    prompt = (
        "Here is the conversation transcript. Analyse it and return the "
        "structured assessment. Use only information the user actually "
        "provided.\n\n--- TRANSCRIPT START ---\n"
        f"{transcript_text}\n"
        "--- TRANSCRIPT END ---"
    )

    last_error: GeminiError | None = None
    for attempt in range(2):
        payload = {
            "systemInstruction": {"parts": [{"text": ANALYSIS_SYSTEM_PROMPT}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": prompt
                            if attempt == 0
                            else (
                                prompt
                                + "\n\nYour previous output could not be parsed. "
                                "Return only valid JSON that matches the schema."
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.15,
                "maxOutputTokens": ASSESSMENT_MAX_OUTPUT_TOKENS,
                "responseMimeType": "application/json",
                "responseSchema": ASSESSMENT_SCHEMA,
            },
        }
        try:
            data = _post_text(payload, timeout=120)
            parsed = _parse_json_response(_extract_text(data))
            return normalize_assessment(parsed, transcript=transcript)
        except GeminiError as exc:
            last_error = exc
            if not exc.retryable:
                raise
            logger.warning("Assessment attempt %s failed: %s", attempt + 1, exc)

    if last_error:
        raise last_error
    raise GeminiError("Gemini could not produce an assessment. Please try again.")


def sanitise_transcript(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in value[:MAX_TRANSCRIPT_MESSAGES]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        cleaned.append({"role": role, "text": text[:MAX_MESSAGE_CHARS]})
    return cleaned


def strip_assessment_marker(text: str) -> tuple[str, bool]:
    ready = bool(re.search(r"\[\[\s*ASSESSMENT_READY\s*\]\]", text or "", re.IGNORECASE))
    cleaned = re.sub(
        r"\[\[\s*ASSESSMENT_READY\s*\]\]", "", text or "", flags=re.IGNORECASE
    ).strip()
    return cleaned, ready
