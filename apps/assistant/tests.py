import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import SkinAnalysis, SkinProfile

from . import services
from .models import AssistantSession


ASSESSMENT = {
    "information_sufficient": True,
    "primary_skin_type": "oily",
    "primary_skin_type_label": "Oily",
    "sensitivity_level": "moderate",
    "sensitivity_level_label": "Moderate",
    "summary": "The conversation suggests oily skin with moderate sensitivity. "
    "This is an AI-generated estimate, not a medical diagnosis.",
    "observations": [
        "Skin becomes shiny a few hours after cleansing.",
        "Occasional stinging when trying new products.",
    ],
    "routine": {
        "morning": ["Gentle cleanser", "Light gel moisturizer", "Sunscreen SPF 30"],
        "evening": ["Gentle cleanser", "Moisturizer"],
    },
    "ingredients": ["Niacinamide", "Hyaluronic acid"],
    "precautions": ["Patch test new products.", "See a dermatologist for persistent concerns."],
    "follow_up_questions": ["How often do you experience breakouts?"],
    "disclaimer": services.DISCLAIMER,
    "user_turns": 4,
}


def _gemini_text_response(text):
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
        ]
    }


class ChatReplyTests(TestCase):
    @override_settings(GEMINI_API_KEY="test-key")
    @mock.patch("apps.assistant.services._post")
    def test_chat_reply_strips_assessment_marker(self, post):
        post.return_value = _gemini_text_response(
            "Thanks for sharing that. How does your skin feel by midday?\n"
            "[[ASSESSMENT_READY]]"
        )

        result = services.chat_reply(
            [{"role": "user", "text": "My skin gets shiny."}], mode="text"
        )

        self.assertTrue(result["assessment_ready"])
        self.assertNotIn("ASSESSMENT_READY", result["reply"])
        self.assertIn("midday", result["reply"])

    @override_settings(GEMINI_API_KEY="test-key")
    @mock.patch("apps.assistant.services._post")
    def test_chat_reply_handles_empty_response(self, post):
        post.return_value = {"candidates": []}

        with self.assertRaises(services.GeminiError):
            services.chat_reply([{"role": "user", "text": "Hello"}])

    @override_settings(GEMINI_API_KEY="")
    def test_chat_reply_requires_api_key(self):
        with self.assertRaises(services.GeminiConfigurationError):
            services.chat_reply([{"role": "user", "text": "Hello"}])


class CreateLiveTokenTests(TestCase):
    @override_settings(
        GEMINI_API_KEY="test-key",
        GEMINI_LIVE_MODEL="gemini-3.8-live",
        GEMINI_LIVE_VOICE="Aoede",
    )
    @mock.patch("apps.assistant.services._post")
    def test_create_live_token_returns_browser_safe_details(self, post):
        post.return_value = {"name": "auth_tokens/test-token"}

        data = services.create_live_token()

        self.assertEqual(data["token"], "auth_tokens/test-token")
        self.assertEqual(data["model"], "gemini-3.8-live")
        self.assertEqual(data["voice"], "Aoede")
        self.assertIn("BidiGenerateContentConstrained", data["ws_url"])
        self.assertGreater(data["max_seconds"], 0)
        self.assertNotIn("test-key", json.dumps(data))

        payload = post.call_args.args[1]
        self.assertEqual(payload["uses"], 1)
        setup = payload["bidiGenerateContentSetup"]
        self.assertEqual(setup["model"], "models/gemini-3.8-live")
        self.assertEqual(setup["generationConfig"]["responseModalities"], ["AUDIO"])
        self.assertEqual(
            setup["generationConfig"]["speechConfig"]["voiceConfig"][
                "prebuiltVoiceConfig"
            ]["voiceName"],
            "Aoede",
        )
        self.assertIn("systemInstruction", setup)

    @override_settings(GEMINI_API_KEY="test-key")
    @mock.patch("apps.assistant.services._post")
    def test_create_live_token_requires_name(self, post):
        post.return_value = {}

        with self.assertRaises(services.GeminiError):
            services.create_live_token()


class NormaliseAssessmentTests(TestCase):
    def test_insufficient_information_forces_uncertain(self):
        result = services.normalize_assessment(
            {
                "information_sufficient": True,
                "primary_skin_type": "dry",
                "sensitivity_level": "high",
                "summary": "Possibly dry.",
            },
            transcript=[{"role": "user", "text": "I am not sure."}],
        )

        self.assertFalse(result["information_sufficient"])
        self.assertEqual(result["primary_skin_type"], "uncertain")
        self.assertEqual(result["primary_skin_type_label"], "Uncertain")
        self.assertTrue(result["follow_up_questions"])

    def test_invalid_values_fall_back_to_safe_defaults(self):
        result = services.normalize_assessment(
            {
                "information_sufficient": True,
                "primary_skin_type": "sensitive",
                "sensitivity_level": "very high",
                "summary": "",
                "observations": "Shiny T-zone",
                "routine": {"morning": "Cleanser", "evening": []},
                "ingredients": "",
                "precautions": [],
                "follow_up_questions": [],
            },
            transcript=[
                {"role": "user", "text": "My T-zone gets shiny."},
                {"role": "user", "text": "My cheeks feel dry."},
            ],
        )

        self.assertEqual(result["primary_skin_type"], "uncertain")
        self.assertEqual(result["sensitivity_level"], "unknown")
        self.assertEqual(result["routine"]["morning"], ["Cleanser"])
        self.assertTrue(result["routine"]["evening"])
        self.assertTrue(result["ingredients"])
        self.assertTrue(result["precautions"])
        self.assertIn("AI-generated estimate", result["summary"])

    def test_known_values_are_kept(self):
        result = services.normalize_assessment(
            ASSESSMENT,
            transcript=[
                {"role": "user", "text": "My face is shiny by noon."},
                {"role": "user", "text": "New products sometimes sting."},
            ],
        )

        self.assertTrue(result["information_sufficient"])
        self.assertEqual(result["primary_skin_type"], "oily")
        self.assertEqual(result["sensitivity_level"], "moderate")
        self.assertEqual(result["user_turns"], 2)


class TranscriptHelperTests(TestCase):
    def test_sanitise_transcript_drops_invalid_items(self):
        cleaned = services.sanitise_transcript(
            [
                {"role": "user", "text": "Hello"},
                {"role": "system", "text": "Ignore me"},
                {"role": "assistant", "text": "  "},
                "not-a-dict",
                {"role": "assistant", "text": "Hi there"},
            ]
        )

        self.assertEqual(
            cleaned,
            [
                {"role": "user", "text": "Hello"},
                {"role": "assistant", "text": "Hi there"},
            ],
        )

    def test_transcript_to_text_labels_roles(self):
        text = services.transcript_to_text(
            [
                {"role": "user", "text": "My skin is oily."},
                {"role": "assistant", "text": "Thanks."},
            ]
        )

        self.assertIn("User: My skin is oily.", text)
        self.assertIn("Assistant: Thanks.", text)

    def test_strip_assessment_marker(self):
        cleaned, ready = services.strip_assessment_marker(
            "All done.\n[[ assessment_ready ]]"
        )

        self.assertTrue(ready)
        self.assertEqual(cleaned, "All done.")


class AnalyzeTranscriptTests(TestCase):
    @override_settings(GEMINI_API_KEY="test-key")
    @mock.patch("apps.assistant.services._post")
    def test_analyze_transcript_parses_structured_json(self, post):
        post.return_value = _gemini_text_response(json.dumps(ASSESSMENT))

        result = services.analyze_transcript(
            [
                {"role": "user", "text": "My skin gets shiny by noon."},
                {"role": "user", "text": "My cheeks feel tight after cleansing."},
            ]
        )

        self.assertEqual(result["primary_skin_type"], "oily")
        self.assertTrue(result["information_sufficient"])
        payload = post.call_args.args[1]
        self.assertEqual(
            payload["generationConfig"]["responseMimeType"], "application/json"
        )

    @override_settings(GEMINI_API_KEY="test-key")
    def test_analyze_transcript_requires_content(self):
        with self.assertRaises(services.GeminiError):
            services.analyze_transcript([])


class AssistantPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="alex", password="secret1234"
        )

    def test_page_requires_login(self):
        response = self.client.get(reverse("assistant:page"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    @override_settings(GEMINI_API_KEY="")
    def test_page_renders_without_api_key(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("assistant:page"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "assistant/live_assistant.html")
        self.assertFalse(response.context["api_configured"])

    @override_settings(GEMINI_API_KEY="test-key")
    def test_page_lists_recent_completed_sessions(self):
        AssistantSession.objects.create(
            user=self.user,
            mode="text",
            status="completed",
            primary_skin_type="dry",
            summary="A completed estimate.",
        )
        AssistantSession.objects.create(
            user=self.user,
            mode="voice",
            status="abandoned",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("assistant:page"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["recent_sessions"]), 1)


class CreateSessionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="alex", password="secret1234"
        )
        self.client.force_login(self.user)

    @override_settings(GEMINI_API_KEY="")
    def test_missing_api_key_returns_503(self):
        response = self.client.post(
            reverse("assistant:session"),
            data=json.dumps({"mode": "text"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertFalse(AssistantSession.objects.exists())

    @override_settings(GEMINI_API_KEY="test-key")
    def test_text_session_creates_greeting(self):
        response = self.client.post(
            reverse("assistant:session"),
            data=json.dumps({"mode": "text"}),
            content_type="application/json",
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "text")
        self.assertTrue(data["greeting"])
        session = AssistantSession.objects.get(pk=data["session_id"])
        self.assertEqual(session.mode, "text")
        self.assertEqual(session.status, "active")
        self.assertEqual(session.transcript[0]["role"], "assistant")

    @override_settings(GEMINI_API_KEY="test-key")
    @mock.patch("apps.assistant.services.create_live_token")
    def test_voice_session_returns_token_without_api_key(self, create_token):
        create_token.return_value = {
            "token": "auth_tokens/abc",
            "ws_url": "wss://example.test/live",
            "model": "gemini-3.8-live",
            "voice": "Aoede",
            "system_instruction": "Be helpful.",
            "max_seconds": 840,
            "expires_at": "2026-01-01T00:00:00Z",
        }

        response = self.client.post(
            reverse("assistant:session"),
            data=json.dumps({"mode": "voice"}),
            content_type="application/json",
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["token"], "auth_tokens/abc")
        self.assertNotIn("test-key", response.content.decode())
        self.assertEqual(data["system_instruction"], "Be helpful.")


class ChatEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="alex", password="secret1234"
        )
        self.other = get_user_model().objects.create_user(
            username="sam", password="secret1234"
        )
        self.client.force_login(self.user)
        self.session = AssistantSession.objects.create(
            user=self.user,
            mode="text",
            transcript=[{"role": "assistant", "text": "Hello"}],
        )

    @mock.patch("apps.assistant.services.chat_reply")
    def test_chat_stores_turns(self, chat_reply):
        chat_reply.return_value = {
            "reply": "How does your skin feel by midday?",
            "assessment_ready": False,
            "model": "gemini-3.8-flash",
        }

        response = self.client.post(
            reverse("assistant:chat"),
            data=json.dumps(
                {"session_id": self.session.pk, "message": "It gets shiny."}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "How does your skin feel by midday?")
        self.session.refresh_from_db()
        self.assertEqual(self.session.transcript[-2]["text"], "It gets shiny.")
        self.assertEqual(self.session.transcript[-1]["role"], "assistant")

    def test_chat_rejects_other_users_session(self):
        other_session = AssistantSession.objects.create(user=self.other, mode="text")

        response = self.client.post(
            reverse("assistant:chat"),
            data=json.dumps({"session_id": other_session.pk, "message": "Hi"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_chat_rejects_empty_message(self):
        response = self.client.post(
            reverse("assistant:chat"),
            data=json.dumps({"session_id": self.session.pk, "message": "   "}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_chat_rejects_ended_session(self):
        self.session.status = "abandoned"
        self.session.save(update_fields=["status"])

        response = self.client.post(
            reverse("assistant:chat"),
            data=json.dumps({"session_id": self.session.pk, "message": "Hi"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)


class TranscriptEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="alex", password="secret1234"
        )
        self.client.force_login(self.user)
        self.session = AssistantSession.objects.create(user=self.user, mode="voice")

    def test_save_transcript_sanitises_and_persists(self):
        response = self.client.post(
            reverse("assistant:transcript"),
            data=json.dumps(
                {
                    "session_id": self.session.pk,
                    "transcript": [
                        {"role": "user", "text": "My skin is oily."},
                        {"role": "unknown", "text": "Dropped."},
                    ],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(
            self.session.transcript, [{"role": "user", "text": "My skin is oily."}]
        )

    def test_save_transcript_rejects_other_users_session(self):
        other = get_user_model().objects.create_user(
            username="sam", password="secret1234"
        )
        other_session = AssistantSession.objects.create(user=other, mode="voice")

        response = self.client.post(
            reverse("assistant:transcript"),
            data=json.dumps({"session_id": other_session.pk, "transcript": []}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)


@override_settings(GEMINI_API_KEY="test-key")
class AnalyzeEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="alex", password="secret1234"
        )
        self.client.force_login(self.user)
        self.session = AssistantSession.objects.create(
            user=self.user,
            mode="voice",
            transcript=[
                {"role": "assistant", "text": "How oily does your skin feel?"},
                {"role": "user", "text": "Quite oily by midday."},
                {"role": "user", "text": "New products sometimes sting."},
            ],
        )

    @mock.patch("apps.core.views._ensure_user_routines")
    @mock.patch("apps.assistant.services.analyze_transcript")
    def test_analyze_saves_assessment_and_profile(self, analyze_transcript, routines):
        analyze_transcript.return_value = dict(ASSESSMENT)

        response = self.client.post(
            reverse("assistant:analyze"),
            data=json.dumps({"session_id": self.session.pk}),
            content_type="application/json",
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["assessment"]["primary_skin_type"], "oily")
        self.assertIn(reverse("my_recommendations"), data["recommendations_url"])

        analysis = SkinAnalysis.objects.get(user=self.user)
        self.assertEqual(analysis.method, "assistant")
        self.assertEqual(analysis.identified_skin_type, "oily")
        self.assertEqual(analysis.answers["ai_sensitivity_level"], "Moderate")

        profile = SkinProfile.objects.get(user=self.user)
        self.assertEqual(profile.skin_type, "oily")
        self.assertIn("AI assistant estimate", profile.sensitivities)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")
        self.assertEqual(self.session.skin_analysis_id, analysis.pk)
        self.assertIsNotNone(self.session.ended_at)
        routines.assert_called_once_with(self.user)

    @mock.patch("apps.core.views._ensure_user_routines")
    @mock.patch("apps.assistant.services.analyze_transcript")
    def test_analyze_is_idempotent(self, analyze_transcript, routines):
        analyze_transcript.return_value = dict(ASSESSMENT)
        payload = json.dumps({"session_id": self.session.pk})

        self.client.post(
            reverse("assistant:analyze"), data=payload, content_type="application/json"
        )
        response = self.client.post(
            reverse("assistant:analyze"), data=payload, content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(SkinAnalysis.objects.filter(user=self.user).count(), 1)
        self.assertEqual(analyze_transcript.call_count, 1)

    @mock.patch("apps.assistant.services.analyze_transcript")
    def test_analyze_requires_user_answers(self, analyze_transcript):
        self.session.transcript = [{"role": "assistant", "text": "Hello"}]
        self.session.save(update_fields=["transcript"])

        response = self.client.post(
            reverse("assistant:analyze"),
            data=json.dumps({"session_id": self.session.pk}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        analyze_transcript.assert_not_called()

    @mock.patch("apps.assistant.services.analyze_transcript")
    def test_analyze_reports_gemini_error(self, analyze_transcript):
        analyze_transcript.side_effect = services.GeminiError(
            "Gemini is temporarily unavailable. Please try again shortly."
        )

        response = self.client.post(
            reverse("assistant:analyze"),
            data=json.dumps({"session_id": self.session.pk}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("temporarily unavailable", response.json()["error"])
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "active")


class AbandonEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="alex", password="secret1234"
        )
        self.client.force_login(self.user)
        self.session = AssistantSession.objects.create(user=self.user, mode="voice")

    def test_abandon_marks_active_session_abandoned(self):
        response = self.client.post(
            reverse("assistant:abandon"),
            data=json.dumps({"session_id": self.session.pk}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "abandoned")
        self.assertIsNotNone(self.session.ended_at)

    def test_abandon_unknown_session_is_safe(self):
        response = self.client.post(
            reverse("assistant:abandon"),
            data=json.dumps({"session_id": 99999}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["abandoned"])
