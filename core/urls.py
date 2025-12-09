import profile

from django.urls import path
from .views import *
urlpatterns = [
    path('', home , name='home'),

    path('dashboard/', dashboard, name='dashboard'),

    #path('profile/<str:user_identifier>/', profile, name='profile'),

    path('register/', register_view, name='register'),
    path('login/',login_view, name='login'),

    path('logout/', logout_view, name='logout'),

    # Unified Search
    path('search/', unified_search, name='search'),  # 💡 NEW

    # Profile URL
    path('profile/<str:user_identifier>/', profile_detail, name='user_profile'),

]