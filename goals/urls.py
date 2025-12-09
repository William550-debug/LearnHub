# learnhub/goals/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Goal List (Kanban Board)
    path('', views.goal_list, name='goal_list'),

    # Goal Creation
    path('create/', views.goal_create, name='goal_create'),

    # 💡 NEW: AJAX Interaction Endpoints
    path('milestone/<int:milestone_pk>/toggle/', views.milestone_toggle, name='milestone_toggle'),
    path('<int:goal_pk>/status/', views.goal_update_status, name='goal_update_status'),
]