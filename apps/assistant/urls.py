from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("", views.assistant_page, name="page"),
    path("session/", views.create_session, name="session"),
    path("session/<int:session_id>/", views.session_detail, name="session_detail"),
    path("history/remove/", views.remove_history_entry, name="remove_history"),
    path("chat/", views.chat, name="chat"),
    path("transcript/", views.save_transcript, name="transcript"),
    path("analyze/", views.analyze, name="analyze"),
    path("abandon/", views.abandon_session, name="abandon"),
]
