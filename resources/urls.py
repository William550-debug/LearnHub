from django.urls import path
from .views import *

urlpatterns = [
    #Resource Browsing
    path('resource_list/',resource_list, name='resource_list'),
    path('add/', resource_create, name='resource_create'),

    path('interact/', resource_interaction, name='resource_interaction'),

    path('<slug:resource_slug>/', resource_detail, name='resource_detail'),
]