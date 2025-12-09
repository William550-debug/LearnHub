from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q,  Case, When
from django.contrib.auth import logout, get_user_model,authenticate,login
from django.db import models
from resources.models import Resource
from django.utils.text import slugify
from core.models import SiteStats, Category, CustomUser, UserProfile ,Skill # Use 'core' models as source
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.utils.decorators import method_decorator
from django.views import View

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 1. AUTHENTICATION VIEWS (Django Built-in Views Handled in URLs)
# ----------------------------------------------------------------------

# NOTE: LoginView and LogoutView are best implemented directly in urls.py
# using Django's built-in views (auth_views.LoginView.as_view(), etc.)
# This avoids writing view code for core security functions.




def logout_view(request):
    """
    This function handles the user logout process. It logs out the user from the current session and redirects them to the login page.

    Parameters:
    request (HttpRequest): The request object containing information about the HTTP request. This parameter is expected to be an instance of Django's HttpRequest class.

    Returns:
    HttpResponseRedirect: A redirect to the login page. This return value indicates that the user has been successfully logged out and redirected to the login page.
    """
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    #redirect user to login page
    return redirect('login')

#GEt the custom user model
User = get_user_model()


def register_view(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        bio = request.POST.get('bio', '').strip()
        skills_input = request.POST.get('skills', '').strip()
        terms_accepted = request.POST.get('terms') == 'on'

        # Validate
        if not all([first_name, email, password1, password2]):
            messages.error(request, 'Please fill all required fields')
            return render(request, 'authentication/registration.html', {'form': request.POST})

        if password1 != password2:
            messages.error(request, 'Passwords do not match')
            return render(request, 'authentication/registration.html', {'form': request.POST})

        if len(password1) < 8:
            messages.error(request, 'Password must be at least 8 characters')
            return render(request, 'authentication/registration.html', {'form': request.POST})

        if not terms_accepted:
            messages.error(request, 'You must agree to the terms')
            return render(request, 'authentication/registration.html', {'form': request.POST})

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered')
            return redirect('login')

        try:
            # Create user
            user = User.objects.create_user(
                email=email,
                password=password1,
                first_name=first_name,
            )

            # Get or create profile
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={'bio': bio}
            )

            if not created:
                # Update existing profile
                profile.bio = bio
                profile.save()

            # Add skills
            if skills_input:
                for skill_name in skills_input.split(','):
                    skill_name = skill_name.strip()
                    if skill_name:
                        skill, _ = Skill.objects.get_or_create(
                            name=skill_name,
                            defaults={'slug': slugify(skill_name)}
                        )
                        profile.skills.add(skill)

            messages.success(request, 'Account created! Please login.')
            return redirect('login')

        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
            return render(request, 'authentication/registration.html', {'form': request.POST})

    return render(request, 'authentication/registration.html')







# Decorators for security
@sensitive_post_parameters('password')
@never_cache
def login_view(request):
    """
    Secure login view with email-based authentication
    """
    # Redirect if already authenticated
    if request.user.is_authenticated:
        messages.info(request, 'You are already logged in.')
        return redirect('home')  # Change to your home/dashboard URL

    # Handle POST request
    if request.method == 'POST':
        email = request.POST.get('username', '').strip().lower()
        password = request.POST.get('password', '')
        remember_me = request.POST.get('remember_me') == 'on'

        # Validate input
        errors = []

        if not email:
            errors.append('Email is required')

        if not password:
            errors.append('Password is required')
        elif len(password) < 1:  # Basic check
            errors.append('Password cannot be empty')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'authentication/login.html', {'form': {'username': email}})

        # Additional email validation
        if '@' not in email or '.' not in email.split('@')[-1]:
            messages.error(request, 'Please enter a valid email address')
            return render(request, 'authentication/login.html', {'form': {'username': email}})

        try:
            # Check if user exists before attempting authentication
            user_exists = User.objects.filter(email=email).exists()

            if not user_exists:
                messages.error(request, 'No account found with this email')
                return render(request, 'authentication/login.html', {'form': {'username': email}})

            # Authenticate user
            user = authenticate(request, username=email, password=password)

            if user is not None:
                # Check if account is active
                if not user.is_active:
                    messages.error(request, 'Your account is inactive. Please contact support.')
                    return render(request, 'authentication/login.html', {'form': {'username': email}})

                # Login successful
                login(request, user)

                # Handle "Remember me"
                if not remember_me:
                    # Session expires when browser closes
                    request.session.set_expiry(0)
                else:
                    # Remember for 30 days
                    request.session.set_expiry(2592000)  # 30 days in seconds

                # Log login activity (optional)
                print(f"User {email} logged in successfully")

                # Get next URL or default redirect
                next_url = request.POST.get('next') or request.GET.get('next') or 'home'

                # Security check: ensure next URL is safe
                from django.utils.http import url_has_allowed_host_and_scheme
                if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    return redirect(next_url)
                else:
                    return redirect('home')

            else:
                # Invalid credentials
                messages.error(request, 'Invalid email or password')
                return render(request, 'authentication/login.html', {'form': {'username': email}})

        except Exception as e:
            # Log the error for debugging
            print(f"Login error: {str(e)}")
            messages.error(request, 'An error occurred during login. Please try again.')
            return render(request, 'authentication/login.html', {'form': {'username': email}})

    # GET request - show login form
    # Pass next parameter to template if present
    context = {}
    next_url = request.GET.get('next')
    if next_url:
        context['next'] = next_url

    return render(request, 'authentication/login.html', context)





# ----------------------------------------------------------------------
# 2. CORE VIEWS
# ----------------------------------------------------------------------


# views.py - Enhanced dashboard view
@login_required
def dashboard(request):
    """
    Authenticated view displaying personalized stats
    """
    # Safely get or create profile
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)
        logger.warning(f"Created missing profile for user: {request.user.email}")

    # Use getattr for safe attribute access
    resources_completed = getattr(profile, 'resources_completed', 0)

    # Check which goal field exists
    if hasattr(profile, 'goals_archived_count'):
        goals_achieved = profile.goals_archived_count
    elif hasattr(profile, 'goals_achieved_count'):
        goals_achieved = profile.goals_achieved_count
    else:
        goals_achieved = 0

    # IMPORTANT: Get user's UPLOADED resources (created by them)
    recent_resources = Resource.objects.filter(
        author=request.user
    ).select_related('category').prefetch_related('tags').order_by('-created_at')[:10]

    # Get resource stats
    total_resources = Resource.objects.filter(author=request.user).count()
    approved_resources = Resource.objects.filter(author=request.user, is_approved=True).count()

    # Get total upvotes received
    from django.db.models import Sum
    total_upvotes_received = Resource.objects.filter(
        author=request.user
    ).aggregate(total_upvotes=Sum('upvote_count'))['total_upvotes'] or 0

    # Get recent activity from other apps if available
    recent_activity = []
    learning_goals = []

    # Try to import and get actual data if apps exist
    try:
        from goals.models import LearningGoal
        learning_goals = LearningGoal.objects.filter(
            user=request.user
        ).order_by('-created_at')[:3]
    except (ImportError, Exception) as e:
        logger.debug(f"Could not load goals: {e}")

    try:
        from resources.models import UserResourceInteraction
        recent_activity = UserResourceInteraction.objects.filter(
            user=request.user
        ).select_related('resource').order_by('-created_at')[:5]
    except (ImportError, Exception) as e:
        logger.debug(f"Could not load recent activity: {e}")

    context = {
        'profile': profile,
        'resources_completed': resources_completed,
        'goals_achieved': goals_achieved,
        'recent_activity': recent_activity,
        'learning_goals': learning_goals,
        # NEW: Add resources data
        'recent_resources': recent_resources,
        'total_resources': total_resources,
        'approved_resources': approved_resources,
        'total_upvotes_received': total_upvotes_received,
        'user': request.user,  # Add user to context
        'is_owner': True,  # Since it's their dashboard
    }

    return render(request, 'dashboard.html', context)


# Simple Home/Landing Page
def home(request):
    """
    Public-facing landing page, redirects authenticated users to the dashboard.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    # Query site-wide statistics (SiteStats model)
    stats = SiteStats.objects.first()

    # Get categories, annotated with resource count
    categories = Category.objects.annotate(
        # Fix: Using 'resources' as related_name as defined in models.py (Phase 2, Step 2)
        resource_count=Count('resources')
    ).order_by('-resource_count')[:8]

    context = {
        'stats': stats,
        'categories': categories,
    }

    # NOTE: The template path should be 'core/index.html'
    return render(request, 'index.html', context)


@login_required()
def profile_detail(request, user_identifier):
    """
    Displays the user's public profile, bio, skills, and shared resources.
    """
    # Query logic: Tries to find by email (primary ID), then falls back to first_name
    try:
        # Tries to get the user using the email (case-insensitive)
        user = CustomUser.objects.get(email__iexact=user_identifier)
    except CustomUser.DoesNotExist:
        # Fallback: Tries to get the user using first_name (less reliable but handles friendly URLs)
        user = get_object_or_404(CustomUser, first_name__iexact=user_identifier)

    # Automatically fetch the related profile (uses the 'profile' related_name)
    profile = user.profile

    # Fetch the user's shared resources (optimized query)
    shared_resources = user.shared_resources.filter(is_approved=True).select_related('category').order_by(
        '-created_at')[:10]

    # Check if the currently logged-in user is viewing their own profile
    is_owner = request.user.is_authenticated and request.user.id == user.id

    context = {
        'profile': profile,
        'shared_resources': shared_resources,
        'target_user': user,
        'is_owner': is_owner,
        # Skills are available via: profile.skills.all
    }

    # NOTE: The template path should be 'core/profile.html'
    return render(request, 'profile.html', context)


def unified_search(request):
    """
    Handles site-wide search across Resources and Users.
    Fulfills Phase 5, Step 3 requirement.
    """
    query = request.GET.get('q', '').strip()

    resource_results = []
    user_results = []

    if query:
        # --- 1. Resource Search (Fulfills Resource, Tag search) ---
        resource_queryset = Resource.objects.filter(is_approved=True).select_related('author',
                                                                                     'category').prefetch_related(
            'tags')

        # Build resource search query (Q object)
        resource_query = (
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(tags__name__icontains=query)
        )

        # Annotate results with interaction status for the current user if logged in (Phase 5)
        if request.user.is_authenticated:
            resource_queryset = resource_queryset.annotate(
                is_upvoted=Case(When(interactions__user=request.user, interactions__upvoted=True, then=True),
                                default=False, output_field=models.BooleanField()),
                is_saved=Case(When(interactions__user=request.user, interactions__saved=True, then=True), default=False,
                              output_field=models.BooleanField())
            )

        resource_results = resource_queryset.filter(resource_query).distinct().order_by('-upvote_count', '-created_at')[
            :20]

        # --- 2. User Search (Fulfills the userSearch) ---
        user_queryset = CustomUser.objects.filter(is_active=True).select_related('profile')

        # Build user search query (Q object)
        user_query = (
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(email__icontains=query) |
                Q(profile__bio__icontains=query)
            # Q(profile__skills__name__contains=query) # Uncomment if you enable Skill searching
        )

        user_results = user_queryset.filter(user_query).distinct().order_by('-date_joined')[:10]

        total_results_count = len(resource_results) + len(user_results)

        context = {
            'query': query,
            'resource_results': resource_results,
            'user_results': user_results,
            'results_count': total_results_count,
        }

        # NOTE: The template path should be 'resources/search.html'
        return render(request, 'resources/search.html', context)

    # Render the search page template even if no query is present
    context = {'query': '', 'resource_results': [], 'user_results': [], 'results_count': 0}
    return render(request, 'resources/search.html', context)