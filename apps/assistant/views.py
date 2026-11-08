import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.models import DailyCheckIn, SkinAnalysis, SkinProfile, SkincareRoutine

from . import services
from .models import AssistantSession
from .prompts import GREETING_TEXT, SKIN_TOPICS, TEXT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _profile_context_text(user) -> str:
    """Describe the signed-in user's saved skin data for the AI system prompt.

    Returns an empty string when the user has no saved profile yet, so the AI
    falls back to its normal general behaviour.
    """
    profile = SkinProfile.objects.filter(user=user).first()
    if profile is None:
        return ""

    lines = []
    skin_type = (
        profile.get_skin_type_display()
        if profile.skin_type != "unknown"
        else "Not yet identified"
    )
    lines.append(f"Identified skin type: {skin_type}")
    if profile.concerns:
        lines.append(f"Skin concerns: {profile.concerns}")
    if profile.sensitivities:
        lines.append(f"Known sensitivities to avoid: {profile.sensitivities}")
    if profile.skincare_goals:
        lines.append(f"Skincare goals: {profile.skincare_goals}")

    for routine in SkincareRoutine.objects.filter(user=user).prefetch_related(
        "steps__product"
    ):
        products = ", ".join(step.product.name for step in routine.steps.all())
        if products:
            lines.append(f"{routine.get_routine_type_display()} routine: {products}")

    latest_checkin = DailyCheckIn.objects.filter(user=user).first()
    if latest_checkin:
        lines.append(
            "Most recent daily check-in: "
            f"{latest_checkin.get_skin_condition_display()} skin on "
            f"{latest_checkin.date:%B %d, %Y} (oiliness {latest_checkin.oiliness}/5, "
            f"dryness {latest_checkin.dryness}/5, acne {latest_checkin.acne_level}/5, "
            f"irritation {latest_checkin.irritation}/5)"
        )

    return (
        "\n\nPROFILE CONTEXT - saved data for the signed-in user. Use it to "
        "tailor your answers, but do not read it out verbatim and do not "
        "mention this list:\n"
        + "\n".join(f"- {line}" for line in lines)
    )


def _json_body(request):
    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _get_session(user, session_id):
    try:
        session_id = int(session_id)
    except (TypeError, ValueError):
        return None
    return AssistantSession.objects.filter(pk=session_id, user=user).first()


def _gemini_error_response(exc: services.GeminiError):
    status = 503 if isinstance(exc, services.GeminiConfigurationError) else 502
    return JsonResponse(
        {"error": exc.public_message, "retryable": exc.retryable}, status=status
    )


def _result_payload(session: AssistantSession) -> dict:
    analysis_url = ""
    if session.skin_analysis_id:
        analysis_url = reverse(
            "assessment_detail", args=[session.skin_analysis_id]
        )
    return {
        "success": True,
        "session_id": session.pk,
        "assessment": session.assessment or {},
        "analysis_id": session.skin_analysis_id,
        "analysis_url": analysis_url,
        "recommendations_url": reverse("my_recommendations"),
    }


@login_required(login_url="login")
def assistant_page(request):
    recent_sessions = (
        AssistantSession.objects.filter(
            user=request.user, status="completed"
        )
        .select_related("skin_analysis")
        .order_by("-ended_at", "-started_at")[:5]
    )
    context = {
        "api_configured": bool((settings.GEMINI_API_KEY or "").strip()),
        "live_model": services.live_model(),
        "text_model": services.text_model(),
        "max_seconds": services.max_session_seconds(),
        "recent_sessions": recent_sessions,
        "skin_topics": SKIN_TOPICS,
        "greeting": GREETING_TEXT,
    }
    return render(request, "assistant/live_assistant.html", context)


@login_required(login_url="login")
@require_POST
def create_session(request):
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"error": "Invalid request."}, status=400)

    mode = payload.get("mode", "voice")
    if mode not in {"voice", "text"}:
        mode = "voice"

    try:
        services.api_key()
    except services.GeminiConfigurationError as exc:
        return _gemini_error_response(exc)

    live_data = None
    if mode == "voice":
        try:
            live_data = services.create_live_token(
                user_context=_profile_context_text(request.user)
            )
        except services.GeminiError as exc:
            return _gemini_error_response(exc)

    session = AssistantSession.objects.create(user=request.user, mode=mode)
    if mode == "text":
        session.transcript = [{"role": "assistant", "text": GREETING_TEXT}]
        session.save(update_fields=["transcript", "updated_at"])

    response = {
        "session_id": session.pk,
        "mode": mode,
        "max_seconds": (
            live_data["max_seconds"]
            if live_data
            else services.max_session_seconds()
        ),
    }
    if mode == "text":
        response["greeting"] = GREETING_TEXT
    if live_data:
        response.update(
            {
                "token": live_data["token"],
                "ws_url": live_data["ws_url"],
                "model": live_data["model"],
                "voice": live_data["voice"],
                "system_instruction": live_data["system_instruction"],
                "expires_at": live_data["expires_at"],
            }
        )
    return JsonResponse(response)


@login_required(login_url="login")
@require_POST
def chat(request):
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"error": "Invalid request."}, status=400)

    session = _get_session(request.user, payload.get("session_id"))
    if session is None:
        return JsonResponse({"error": "Conversation not found."}, status=404)
    if session.status != "active":
        return JsonResponse(
            {"error": "This conversation has ended. Restart to begin a new one."},
            status=409,
        )

    message = str(payload.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "Type a message first."}, status=400)
    if len(message) > services.MAX_MESSAGE_CHARS:
        return JsonResponse(
            {"error": "That message is too long. Please shorten it."}, status=400
        )

    history = list(session.transcript or [])
    history.append({"role": "user", "text": message})

    try:
        result = services.chat_reply(
            history,
            mode="text",
            system_prompt=TEXT_SYSTEM_PROMPT + _profile_context_text(request.user),
        )
    except services.GeminiError as exc:
        return _gemini_error_response(exc)

    history.append({"role": "assistant", "text": result["reply"]})
    session.transcript = history[-services.MAX_TRANSCRIPT_MESSAGES :]
    session.save(update_fields=["transcript", "updated_at"])

    return JsonResponse(
        {
            "success": True,
            "reply": result["reply"],
            "assessment_ready": result["assessment_ready"],
            "session_id": session.pk,
        }
    )


@login_required(login_url="login")
@require_POST
def save_transcript(request):
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"error": "Invalid request."}, status=400)

    session = _get_session(request.user, payload.get("session_id"))
    if session is None:
        return JsonResponse({"error": "Conversation not found."}, status=404)

    transcript = services.sanitise_transcript(payload.get("transcript"))
    if transcript:
        session.transcript = transcript
        session.save(update_fields=["transcript", "updated_at"])

    return JsonResponse({"success": True, "messages": len(session.transcript or [])})


@login_required(login_url="login")
@require_POST
def analyze(request):
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"error": "Invalid request."}, status=400)

    session = _get_session(request.user, payload.get("session_id"))
    if session is None:
        return JsonResponse({"error": "Conversation not found."}, status=404)

    if session.assessment and session.skin_analysis_id:
        return JsonResponse(_result_payload(session))

    incoming = services.sanitise_transcript(payload.get("transcript"))
    if incoming:
        session.transcript = incoming
        session.save(update_fields=["transcript", "updated_at"])

    transcript = list(session.transcript or [])
    user_turns = sum(
        1
        for item in transcript
        if item.get("role") == "user" and len(str(item.get("text") or "").strip()) >= 3
    )
    if user_turns == 0:
        return JsonResponse(
            {
                "error": (
                    "There is not enough conversation to assess yet. Start the "
                    "conversation and answer at least one question."
                )
            },
            status=400,
        )

    try:
        assessment = services.analyze_transcript(transcript)
    except services.GeminiError as exc:
        return _gemini_error_response(exc)
    except Exception:
        logger.exception("Unexpected assistant analysis failure for user %s", request.user.pk)
        return JsonResponse(
            {"error": "The assessment could not be completed. Please try again."},
            status=500,
        )

    mapped_skin_type = {
        "oily": "oily",
        "dry": "dry",
        "normal": "normal",
        "combination": "combination",
        "uncertain": "unknown",
    }.get(assessment["primary_skin_type"], "unknown")

    answers = {
        "ai_primary_skin_type": assessment["primary_skin_type_label"],
        "ai_sensitivity_level": assessment["sensitivity_level_label"],
        "ai_summary": assessment["summary"],
        "ai_observations": "; ".join(assessment["observations"]),
        "ai_morning_routine": "; ".join(assessment["routine"]["morning"]),
        "ai_evening_routine": "; ".join(assessment["routine"]["evening"]),
        "ai_ingredients": ", ".join(assessment["ingredients"]),
        "ai_precautions": "; ".join(assessment["precautions"]),
        "ai_follow_up": "; ".join(assessment["follow_up_questions"]) or "None",
    }

    analysis = SkinAnalysis.objects.create(
        user=request.user,
        method="assistant",
        identified_skin_type=mapped_skin_type,
        answers=answers,
        notes=assessment["summary"],
    )

    profile, _ = SkinProfile.objects.get_or_create(user=request.user)
    if assessment["information_sufficient"] and mapped_skin_type != "unknown":
        profile.skin_type = mapped_skin_type

    sensitivity_key = assessment["sensitivity_level"]
    if sensitivity_key in {"low", "moderate", "high"}:
        existing_lines = [
            line
            for line in (profile.sensitivities or "").splitlines()
            if not line.startswith("AI assistant estimate")
        ]
        existing_lines.append(
            "AI assistant estimate ({}): {} sensitivity".format(
                timezone.localdate().strftime("%b %d, %Y"),
                assessment["sensitivity_level_label"],
            )
        )
        profile.sensitivities = "\n".join(existing_lines).strip()[:2000]
    profile.save()

    try:
        from apps.core.views import _ensure_user_routines

        _ensure_user_routines(request.user)
    except Exception:
        logger.exception(
            "Could not refresh routines after assistant assessment for user %s",
            request.user.pk,
        )

    session.status = "completed"
    session.ended_at = timezone.now()
    session.assessment = assessment
    session.primary_skin_type = assessment["primary_skin_type"]
    session.sensitivity_level = assessment["sensitivity_level"]
    session.summary = assessment["summary"]
    session.skin_analysis = analysis
    session.save()

    return JsonResponse(_result_payload(session))


@login_required(login_url="login")
@require_POST
def abandon_session(request):
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"error": "Invalid request."}, status=400)

    session = _get_session(request.user, payload.get("session_id"))
    if session is None:
        return JsonResponse({"success": True, "abandoned": False})

    if session.status == "active":
        session.status = "abandoned"
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at", "updated_at"])

    return JsonResponse({"success": True, "abandoned": True})
