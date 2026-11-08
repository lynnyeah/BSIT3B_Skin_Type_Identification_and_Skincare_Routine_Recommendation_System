from django.contrib import admin

from .models import AssistantSession


@admin.register(AssistantSession)
class AssistantSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "mode",
        "status",
        "primary_skin_type",
        "sensitivity_level",
        "started_at",
        "ended_at",
    )
    list_filter = ("mode", "status", "primary_skin_type", "sensitivity_level")
    search_fields = ("user__username", "user__email", "summary")
    readonly_fields = (
        "user",
        "mode",
        "status",
        "transcript",
        "assessment",
        "primary_skin_type",
        "sensitivity_level",
        "summary",
        "skin_analysis",
        "started_at",
        "ended_at",
        "updated_at",
    )
    ordering = ("-started_at",)

    def has_add_permission(self, request):
        return False
