from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('home/', views.home, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('skin-analysis/', views.skin_analysis, name='skin_analysis'),
    path('my-recommendations/', views.my_recommendations, name='my_recommendations'),
    path('routine-planner/', views.routine_planner, name='routine_planner'),
    path('toggle-step/', views.toggle_step_completion, name='toggle_step_completion'),
    path('add-routine-step/', views.add_routine_step, name='add_routine_step'),
    path('update-preferences/', views.update_preferences, name='update_preferences'),
    path('assessment-history/', views.assessment_history, name='assessment_history'),
    path('assessment-history/<int:pk>/', views.assessment_detail, name='assessment_detail'),
    path('assessment-history/compare/', views.assessment_compare, name='assessment_compare'),
    path('my-profile/', views.my_profile, name='my_profile'),
]