"""Throwaway live end-to-end check for the assistant (hits real Gemini)."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class LiveAssistantE2E(TestCase):
    def test_full_text_session(self):
        user = get_user_model().objects.create_user(
            username="e2e_live_test", email="e2e@test.local", password="pw12345!"
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("assistant:session"),
            data=json.dumps({"mode": "text"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content[:500])
        payload = response.json()
        self.assertTrue(payload.get("session_id"), payload)

        answers = [
            "My T-zone gets shiny and greasy a couple of hours after washing, "
            "but my cheeks feel normal, not dry or tight.",
            "I get small breakouts on my forehead around twice a month, and my "
            "pores look visible on my nose.",
            "My skin rarely flakes, and I have not noticed stinging with new "
            "products, though my face does flush a little in hot weather.",
        ]
        for answer in answers:
            response = self.client.post(
                reverse("assistant:chat"),
                data=json.dumps(
                    {"session_id": payload["session_id"], "message": answer}
                ),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200, response.content[:500])
            data = response.json()
            self.assertTrue(data.get("reply"))
            print("AI REPLY:", data["reply"][:200].replace("\n", " "))

        response = self.client.post(
            reverse("assistant:analyze"),
            data=json.dumps({"session_id": payload["session_id"]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content[:800])
        result = response.json()
        print(
            "ASSESSMENT:",
            json.dumps(
                result.get("assessment", {}),
                indent=1,
            )[:1200],
        )
        print("ANALYSIS URL:", result.get("analysis_url"))
