from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('home/', views.home, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('skin-analysis/', views.skin_analysis, name='skin_analysis'),
    path('routine-planner/', views.routine_planner, name='routine_planner'),
    path('my-recommendations/', views.my_recommendations_redirect, name='my_recommendations'),
    path('toggle-step/', views.toggle_step_completion, name='toggle_step_completion'),
    path('add-routine-step/', views.add_routine_step, name='add_routine_step'),
    path('update-preferences/', views.update_preferences, name='update_preferences'),
    path('assessment-history/', views.skin_progress_history, name='assessment_history'),
    path('assessment-history/checkin/save/', views.checkin_save, name='checkin_save'),
    path('assessment-history/checkin/delete/', views.checkin_delete, name='checkin_delete'),
    path('assessment-history/checkin/photo-delete/', views.checkin_photo_delete, name='checkin_photo_delete'),
    path('assessment-history/day-details/', views.checkin_day_details, name='checkin_day_details'),
    path('assessment-history/ingredient-experience/save/', views.ingredient_experience_save, name='ingredient_experience_save'),
    path('assessment-history/<int:pk>/', views.assessment_detail, name='assessment_detail'),
    path('my-profile/', views.my_profile, name='my_profile'),
]