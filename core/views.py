from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Case, When, Sum
from django.contrib.auth import logout, get_user_model,authenticate,login
from django.db import models
# FIX: Import BaseResource, which is the functional replacement for the old Resource model.
# Also import concrete models for type checking if needed later.

from goals.models import LearningGoal
from resources.models import  BaseResource , UserResourceInteraction , Book , Article, Course
from django.utils.text import slugify
from core.models import SiteStats, Category, CustomUser, UserProfile ,Skill # Use 'core' models as source
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.utils.decorators import method_decorator
from django.views import View
from django.utils.http import url_has_allowed_host_and_scheme # Keep import here for clarity
from itertools import chain

import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 1. AUTHENTICATION VIEWS (Django Built-in Views Handled in URLs)
# ----------------------------------------------------------------------

def logout_view(request):
    """
    This function handles the user logout process. It logs out the user from the current session and redirects them to the login page.
    ...
    """
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    #redirect user to login page
    return redirect('login')

#GEt the custom user model
User = get_user_model()


def register_view(request):
    # ... (Register view logic unchanged) ...
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
    # ... (Login view logic unchanged) ...
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
    Authenticated view displaying personalized stats and recent user activity.
    """
    user = request.user

    # Safely get or create profile
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=user)
        logger.warning(f"Created missing profile for user: {user.email}")

    # Safely retrieve stats from profile
    resources_completed = getattr(profile, 'resources_completed', 0)

    # Check which goal field exists
    goals_achieved = 0
    if hasattr(profile, 'goals_archived_count'):
        goals_achieved = profile.goals_archived_count
    elif hasattr(profile, 'goals_achieved_count'):
        goals_achieved = profile.goals_achieved_count

    # --- 1. Get recent resources (Fixing the UNION error) ---

    # Query top resources from each concrete model and combine/sort in Python.
    # This avoids the SQL UNION error and preserves model instance functionality.

    recent_resources_list = []

    # Query 10 of each type uploaded by the user
    recent_resources_list.extend(
        Book.objects.filter(author=user)
        .select_related('category')
        .prefetch_related('tags')
        .order_by('-created_at')[:10]
    )

    recent_resources_list.extend(
        Article.objects.filter(author=user)
        .select_related('category')
        .prefetch_related('tags')
        .order_by('-created_at')[:10]
    )

    recent_resources_list.extend(
        Course.objects.filter(author=user)
        .select_related('category')
        .prefetch_related('tags')
        .order_by('-created_at')[:10]
    )

    # Sort the combined list in Python and take the final top 10
    recent_resources = sorted(
        recent_resources_list,
        key=lambda r: r.created_at,
        reverse=True
    )[:10]

    # --- 2. Get resource stats (Counts) ---

    total_resources = (
            Book.objects.filter(author=user).count() +
            Article.objects.filter(author=user).count() +
            Course.objects.filter(author=user).count()
    )

    approved_resources = (
            Book.objects.filter(author=user, is_approved=True).count() +
            Article.objects.filter(author=user, is_approved=True).count() +
            Course.objects.filter(author=user, is_approved=True).count()
    )

    # --- 3. Get total upvotes received (Fixing the TypeError) ---

    # Must use parentheses to ensure `or 0` resolves None before summation
    total_upvotes_received = (
            (Book.objects.filter(author=user)
             .aggregate(total_upvotes=Sum('upvote_count'))['total_upvotes'] or 0)
            +
            (Article.objects.filter(author=user)
             .aggregate(total_upvotes=Sum('upvote_count'))['total_upvotes'] or 0)
            +
            (Course.objects.filter(author=user)
             .aggregate(total_upvotes=Sum('upvote_count'))['total_upvotes'] or 0)
    )

    # --- 4. Get Learning Goals ---
    learning_goals = []
    try:
        learning_goals = LearningGoal.objects.filter(
            user=user
        ).order_by('-created_at')[:3]
    except Exception as e:
        logger.debug(f"Could not load goals: {e}")

    # --- 5. Context preparation ---

    context = {
        'profile': profile,
        'resources_completed': resources_completed,
        'goals_achieved': goals_achieved,
        'learning_goals': learning_goals,

        # Resources data
        'recent_resources': recent_resources,
        'total_resources': total_resources,
        'approved_resources': approved_resources,
        'total_upvotes_received': total_upvotes_received,

        'user': user,
        'is_owner': True,

        # Placeholder stats for completeness (you can implement these later)
        'learning_time': 0,
        'learning_time_change': 0,
        'streak_days': 0,
    }

    return render(request, 'dashboard.html', context)


# Simple Home/Landing Page
def home(request):
    """
    Public-facing landing page. Fixed FieldError by using specific related_names
    for each concrete resource type.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    # Query site-wide statistics
    stats = SiteStats.objects.first()

    # Get categories, annotated with the sum of all resource types
    categories = Category.objects.annotate(
        article_count=Count('resources_article_resources', distinct=True),
        book_count=Count('resources_book_resources', distinct=True),
        course_count=Count('resources_course_resources', distinct=True)
    ).annotate(
        # Sum the counts together for the total 'resource_count'
        resource_count=(
            models.F('article_count') +
            models.F('book_count') +
            models.F('course_count')
        )
    ).order_by('-resource_count')[:8]

    context = {
        'stats': stats,
        'categories': categories,
    }

    return render(request, 'index.html', context)


@login_required()
def profile_detail(request, user_identifier):
    """
    Displays the user's public profile, bio, skills, and shared resources.

    The function handles fetching the user, profile, and combining
    resources from all concrete models (Book, Article, Course).
    """
    # 1. Fetch Target User
    try:
        # Prioritize email lookup
        target_user = CustomUser.objects.get(email__iexact=user_identifier)
    except CustomUser.DoesNotExist:
        # Fallback to get_object_or_404 based on first_name/username (as per your original code)
        target_user = get_object_or_404(CustomUser, first_name__iexact=user_identifier)

    profile = target_user.profile

    # Check if the currently logged-in user is the profile owner
    is_owner = request.user.is_authenticated and request.user.id == target_user.id

    # 2. Fetch Shared Resources (CRITICAL FIX)

    # We must explicitly query each concrete resource model using the shared 'author' field.

    # Note: Book, Article, and Course must be imported at the top of views.py (they are).

    # Fetch approved resources for the target_user, including related fields for the template
    approved_books = Book.objects.filter(author=target_user, is_approved=True).select_related(
        'category').prefetch_related('tags')
    approved_articles = Article.objects.filter(author=target_user, is_approved=True).select_related(
        'category').prefetch_related('tags')
    approved_courses = Course.objects.filter(author=target_user, is_approved=True).select_related(
        'category').prefetch_related('tags')

    # Chain the querysets together. This returns an iterator of model instances.
    shared_resources_qs = chain(approved_books, approved_articles, approved_courses)

    # Convert to list and sort by created_at, then limit to the top 10
    shared_resources = sorted(
        list(shared_resources_qs),
        key=lambda x: x.created_at,
        reverse=True
    )[:10]

    # 3. Calculate Aggregated Stats (Optimized for the template)

    # Total upvotes received
    total_upvotes = (
            (Book.objects.filter(author=target_user).aggregate(total=Sum('upvote_count'))['total'] or 0) +
            (Article.objects.filter(author=target_user).aggregate(total=Sum('upvote_count'))['total'] or 0) +
            (Course.objects.filter(author=target_user).aggregate(total=Sum('upvote_count'))['total'] or 0)
    )

    # Total comments received (Requires complex aggregation or simple list sum)
    # Since resources are heterogeneous, we sum the comment count on the list itself:
    # core/views.py (Inside profile_detail, Final Fix for Calculation)

    # 3. Calculate Aggregated Stats (Optimized for the template)
    # ... (total_upvotes calculation remains unchanged) ...

    # Total comments received (Requires complex aggregation or simple list sum)
    # Use a defensive check (hasattr) to ensure the attribute exists on the resource instance
    total_comments_received = sum(
        resource.comments.count()
        for resource in shared_resources
        if hasattr(resource, 'comments')  # <-- Defensive check added
    )
    # NOTE: This only counts comments on the top 10 resources.
    # NOTE: This only counts comments on the top 10 resources. For an accurate total,
    # you would need a more complex query targeting the Comment model.

    # 4. Context Preparation
    context = {
        'profile': profile,
        'shared_resources': shared_resources,
        'target_user': target_user,
        'is_owner': is_owner,

        # New context variables for template stats
        'total_upvotes': total_upvotes,
        'total_comments_received': total_comments_received,
    }

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
        # FIX: Target BaseResource for unified search
        resource_queryset = BaseResource.objects.filter(is_approved=True).select_related('author',
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