from django.urls import reverse
from django.utils import timezone

from .models import RoutineProgress


def header_context(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    notifications = []

    latest_analysis = user.skin_analyses.order_by("-created_at").first()
    if latest_analysis:
        notifications.append(
            {
                "id": "analysis-ready",
                "title": "Skin analysis ready",
                "message": (
                    f"Your latest result is "
                    f"{latest_analysis.get_identified_skin_type_display()}."
                ),
                "url": reverse("assessment_history"),
                "icon": "fa-solid fa-wand-magic-sparkles",
                "tone": "rose",
            }
        )
    else:
        notifications.append(
            {
                "id": "analysis-todo",
                "title": "Complete your skin analysis",
                "message": "Find out your skin type to unlock tailored recommendations.",
                "url": reverse("skin_analysis"),
                "icon": "fa-solid fa-magnifying-glass",
                "tone": "rose",
            }
        )

    routines = list(user.skincare_routines.prefetch_related("steps").all())
    if not routines:
        notifications.append(
            {
                "id": "routine-setup",
                "title": "Build your skincare routine",
                "message": "Your morning and evening routines are ready to be set up.",
                "url": reverse("routine_planner"),
                "icon": "fa-solid fa-list-check",
                "tone": "sage",
            }
        )
    else:
        today = timezone.localdate()
        progress_entries = RoutineProgress.objects.filter(
            user=user,
            date=today,
            routine__in=routines,
        )
        completed_by_routine = {
            entry.routine_id: set(entry.completed_steps or [])
            for entry in progress_entries
        }

        total_steps = 0
        completed_steps = 0
        for routine in routines:
            step_ids = {step.id for step in routine.steps.all()}
            total_steps += len(step_ids)
            completed_steps += len(step_ids & completed_by_routine.get(routine.id, set()))

        remaining_steps = max(total_steps - completed_steps, 0)

        if total_steps and remaining_steps:
            notifications.append(
                {
                    "id": "routine-remaining",
                    "title": "Today's routine is waiting",
                    "message": (
                        f"{remaining_steps} step"
                        f"{'' if remaining_steps == 1 else 's'} left to complete today."
                    ),
                    "url": reverse("routine_planner"),
                    "icon": "fa-solid fa-calendar-check",
                    "tone": "sand",
                }
            )
        elif total_steps:
            notifications.append(
                {
                    "id": "routine-complete",
                    "title": "Routine complete",
                    "message": "You finished every step for today. Keep it up!",
                    "url": reverse("routine_planner"),
                    "icon": "fa-solid fa-circle-check",
                    "tone": "sage",
                }
            )

    profile = getattr(user, "user_profile", None)
    avatar_url = ""
    if profile and profile.avatar:
        avatar_url = profile.avatar.url

    theme = ""
    preferences = getattr(user, "preferences", None)
    if preferences is not None:
        theme = preferences.theme

    display_name = user.get_full_name().strip() or user.username
    initials = "".join(
        part[0].upper() for part in (user.first_name, user.last_name) if part
    )
    if not initials:
        initials = user.username[:1].upper()

    return {
        "topbar_notifications": notifications,
        "topbar_notification_count": len(notifications),
        "topbar_display_name": display_name,
        "topbar_initials": initials,
        "topbar_avatar_url": avatar_url,
        "topbar_role": "Administrator" if user.is_superuser else "Member",
        "topbar_theme": theme,
    }
