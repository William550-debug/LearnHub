# resources/urls.py (Final URL configuration)

from django.urls import path
from .views import (
    resource_list,
    resource_create,
    resource_detail,
    # resource_interaction,
    # course_progress_update,
    add_comment,  # NEW
    resource_update, resource_interaction, course_enroll, generate_course_ajax, regenerate_course_roadmap,
    course_analytics,  # NEW
)

urlpatterns = [
    # Resource Browsing
    path('list/', resource_list, name='resource_list'),

    # Creation and Update
    path('add/<str:resource_type>/', resource_create, name='resource_create'),
    path('<slug:resource_slug>/edit/', resource_update, name='resource_update'),  # Edit URL

    # Detail View (Must be last due to slug)
    path('<slug:resource_slug>/', resource_detail, name='resource_detail'),

    # Interactions
   path('resource/interaction/', resource_interaction, name='resource_interaction'),
    #path('ajax/progress/', course_progress_update, name='course_progress_update'),

    #course progress
    path('course/<int:course_id>/enroll/', course_enroll, name='course_enroll'),

    # Comments
    path('<slug:resource_slug>/comment/', add_comment, name='add_comment'),  # Comment URL

    path('course/generate-ajax/', generate_course_ajax, name='generate_course_ajax'),
    path('course/<int:course_id>/regenerate/', regenerate_course_roadmap, name='regenerate_roadmap'),

    path('course/<int:course_id>/analytics/', course_analytics, name='course_analytics'),
]