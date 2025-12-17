# resources/urls.py (Final URL configuration)

from django.urls import path
from .views import (
    resource_list,
    resource_create,
    resource_detail,
    # resource_interaction,
    # course_progress_update,
    add_comment,  # NEW
    resource_update, resource_interaction,  # NEW
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

    # Comments
    path('<slug:resource_slug>/comment/', add_comment, name='add_comment'),  # Comment URL
]