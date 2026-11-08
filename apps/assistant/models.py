from django.conf import settings
from django.db import models


class AssistantSession(models.Model):
    """Stores one Gemini skincare conversation and its final assessment.

    The structured result is also copied into the existing SkinAnalysis model
    so it appears in assessment history and can drive the existing
    recommendation/routine features.
    """

    MODES = [
        ("voice", "Voice"),
        ("text", "Text"),
    ]

    STATUSES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("abandoned", "Abandoned"),
        ("error", "Error"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_sessions",
    )
    mode = models.CharField(max_length=10, choices=MODES, default="voice")
    status = models.CharField(max_length=12, choices=STATUSES, default="active")
    transcript = models.JSONField(default=list, blank=True)
    assessment = models.JSONField(default=dict, blank=True)
    primary_skin_type = models.CharField(max_length=20, blank=True)
    sensitivity_level = models.CharField(max_length=20, blank=True)
    summary = models.TextField(blank=True)
    skin_analysis = models.OneToOneField(
        "core.SkinAnalysis",
        on_delete=models.SET_NULL,
        related_name="assistant_session",
        null=True,
        blank=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "-started_at"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.get_mode_display()} - {self.started_at:%Y-%m-%d %H:%M}"
