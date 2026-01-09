from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Count, Q, Case, When, BooleanField, IntegerField, F, Value
from django.db import transaction
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest, Http404
import logging
from datetime import timedelta, timezone

from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
from django.core.cache import cache
# Import all concrete models and the base model
from .models import BaseResource, Book, Article, Course, Tag, UserResourceInteraction, Comment, CourseProgress, \
    ModuleProgress, UserLearningStats
from core.models import Category
from goals.models import LearningGoal
# Import all new forms
from .forms import BookForm, ArticleForm, CourseForm
# Import the new helper files
from .services import enroll_user_in_course
from .mixins import get_concrete_resource_type
from django.contrib.contenttypes.models import ContentType
from .course_tools import generate_course_roadmap  # Updated to use DeepSeek

logger = logging.getLogger(__name__)


# --- 1. Resource List View (Optimized) ---
@login_required(login_url='login')
def resource_list(request):
    """
    Optimized resource list view that aggregates all resource types
    """
    try:
        # Combine all approved resources from all concrete models
        all_resources = []

        # Get resources from each model
        for model in [Book, Article, Course]:
            resources = model.objects.filter(is_approved=True).select_related(
                'author', 'category'
            ).prefetch_related('tags')[:50]  # Limit to prevent performance issues
            all_resources.extend(list(resources))

        # Sort by creation date (newest first)
        all_resources.sort(key=lambda x: x.created_at, reverse=True)

        # Pagination
        paginator = Paginator(all_resources, 12)
        page_number = request.GET.get('page', 1)

        try:
            page_obj = paginator.page(page_number)
        except (PageNotAnInteger, EmptyPage):
            page_obj = paginator.page(1)

        # Add interaction annotations for authenticated users
        if request.user.is_authenticated:
            for resource in page_obj.object_list:
                resource_type = ContentType.objects.get_for_model(resource.__class__)
                interaction = UserResourceInteraction.objects.filter(
                    user=request.user,
                    content_type=resource_type,
                    object_id=resource.pk
                ).first()

                resource.user_interaction = interaction
                resource.is_upvoted = interaction.upvoted if interaction else False
                resource.is_saved = interaction.saved if interaction else False

        return render(request, 'resources/resource_list.html', {
            'page_obj': page_obj,
            'resources': page_obj.object_list,
            'categories': Category.objects.all(),
            'total_count': len(all_resources),
        })

    except Exception as e:
        logger.error(f"Error in resource_list: {str(e)}")
        messages.error(request, "Unable to load resources. Please try again.")
        return render(request, 'resources/resource_list.html', {
            'page_obj': [],
            'resources': [],
            'categories': Category.objects.all(),
            'total_count': 0,
        })


# --- 2. Resource Detail View (Optimized) ---
def resource_detail(request, resource_slug):
    """
    Displays the detail page for any concrete resource type (Book, Article, Course).
    Integrates AI roadmap persistence and Goals app progress tracking.
    """
    try:
        # 1. Find the resource using the slug across all concrete types
        resource = None
        resource_model = None

        for model in [Book, Article, Course]:
            try:
                found_resource = model.objects.get(slug=resource_slug, is_approved=True)
                resource = found_resource
                resource_model = model
                break
            except model.DoesNotExist:
                continue

        if not resource:
            raise Http404("Resource not found or not approved.")

    except Http404:
        messages.error(request, 'Resource not found or not approved')
        return redirect('resource_list')
    except Exception as e:
        logger.error(f"Error finding resource {resource_slug}: {str(e)}")
        messages.error(request, 'An error occurred while loading the resource.')
        return redirect('resource_list')

    try:
        # 2. Basic Metadata & Comments
        resource_content_type = ContentType.objects.get_for_model(resource_model)
        comments = Comment.objects.filter(
            content_type=resource_content_type,
            object_id=resource.pk,
            parent__isnull=True
        ).select_related('author').order_by('-created_at')[:50]

        # 3. User Interaction (Likes/Bookmarks)
        user_interaction = None
        if request.user.is_authenticated:
            user_interaction = UserResourceInteraction.objects.filter(
                user=request.user,
                content_type=resource_content_type,
                object_id=resource.pk
            ).first()

        user_is_creator = request.user.is_authenticated and request.user == resource.author

        # 4. Course-Specific Logic (Roadmap & Goals Integration)
        course_roadmap = None
        user_goal = None
        enrollment_status = False

        if isinstance(resource, Course):
            # Get existing roadmap or generate new one
            course_roadmap = resource.get_roadmap()

            if not course_roadmap:
                # Generate roadmap only if it doesn't exist
                try:
                    course_roadmap = generate_course_roadmap(resource)
                    messages.info(request, 'Course roadmap generated successfully!')
                except Exception as e:
                    logger.error(f"Error generating roadmap for course {resource.id}: {str(e)}")
                    course_roadmap = []
                    messages.warning(request, 'Could not generate AI roadmap. Showing basic course content.')

            # 5. GOALS APP INTEGRATION: Fetch progress tracking object
            if request.user.is_authenticated:
                # Check if user is enrolled
                enrollment_status = CourseProgress.objects.filter(
                    user=request.user,
                    course=resource
                ).exists()

                # Link the course to the LearningGoal via Generic Foreign Key
                user_goal = LearningGoal.objects.filter(
                    user=request.user,
                    content_type=resource_content_type,
                    object_id=resource.id
                ).first()

                # MAPPING: Match Roadmap Videos to Goal Milestones for the UI
                if user_goal:
                    milestones = user_goal.milestones.all()
                    # We attach the actual milestone ID to the roadmap data for the AJAX buttons
                    for module in course_roadmap:
                        for video in module.get('videos', []):
                            # Find the milestone that matches this video title
                            match = milestones.filter(title__icontains=video.get('title', '')).first()
                            if match:
                                video['milestone_id'] = match.id
                                video['is_completed'] = match.is_completed

        # 6. Similar Resources logic
        similar_resources = []
        try:
            for model in [Book, Article, Course]:
                if not isinstance(resource, model):
                    similar = model.objects.filter(
                        category=resource.category,
                        is_approved=True
                    ).exclude(pk=resource.pk).order_by('?')[:2]
                    similar_resources.extend(list(similar))

            if len(similar_resources) < 3:
                same_type = resource.__class__.objects.filter(
                    category=resource.category,
                    is_approved=True
                ).exclude(pk=resource.pk).order_by('?')[:3]
                similar_resources.extend(list(same_type))

            import random
            random.shuffle(similar_resources)
        except Exception as e:
            logger.error(f"Error finding similar resources: {str(e)}")
            similar_resources = []

        context = {
            'resource': resource,
            'resource_type': resource.get_resource_type(),
            'comments': comments,
            'user_goal': user_goal,  # Essential for the progress bar
            'user_interaction': user_interaction,
            'user_is_creator': user_is_creator,
            'similar_resources': similar_resources[:3],
            'course_roadmap': course_roadmap,
            'enrollment_status': enrollment_status if isinstance(resource, Course) else False,
        }

        template_name = f'resources/Details/{resource.get_resource_type().lower()}_detail.html'
        return render(request, template_name, context)

    except Exception as e:
        logger.error(f"Error in resource_detail for {resource_slug}: {str(e)}")
        messages.error(request, 'An error occurred while loading the resource details.')
        return redirect('resource_list')


# --- 3. Resource Creation View (Optimized) ---
@login_required
def resource_create(request, resource_type=None):
    """
    View for creating new resources of a specific type (book, article, or course).
    """
    # Use 'article' as default if resource_type is not provided
    resource_type = resource_type or request.POST.get('resource_type', 'article')

    # Map resource types to forms and models
    form_map = {
        'book': (BookForm, Book),
        'article': (ArticleForm, Article),
        'course': (CourseForm, Course),
    }

    if resource_type not in form_map:
        messages.error(request, f"Invalid resource type: {resource_type}")
        return redirect('resource_list')

    ResourceFormClass, ResourceModel = form_map[resource_type]

    # Initialize all form variables
    article_form, book_form, course_form = None, None, None
    form = None

    if request.method == 'POST':
        form = ResourceFormClass(request.POST, request.FILES)

        # When a POST fails, re-instantiate the *other* forms for context
        if resource_type != 'article':
            article_form = ArticleForm()
        if resource_type != 'book':
            book_form = BookForm()
        if resource_type != 'course':
            course_form = CourseForm()

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the resource instance
                    resource = form.save(commit=False)
                    resource.author = request.user

                    # For courses, don't auto-generate roadmap (let detail view handle it)
                    resource.save()
                    form.save_m2m()  # Save tags

                logger.info(f"{resource_type} created: {resource.title} by {request.user.email}")
                messages.success(request,
                                 f'{resource_type.capitalize()} created successfully! Awaiting admin approval.')

                return redirect('resource_detail', resource_slug=resource.slug)

            except Exception as e:
                logger.error(f"Error creating {resource_type}: {str(e)}")
                messages.error(request, f'Error creating resource: {str(e)}')
        else:
            logger.warning(f"{resource_type} form validation errors: {form.errors}")
            messages.error(request, 'Please correct the errors below.')
    else:
        # GET Request: Instantiate all forms for the initial tabbed display
        article_form = ArticleForm()
        book_form = BookForm()
        course_form = CourseForm()
        form = ResourceFormClass()

    context = {
        'form': form,
        'edit_mode': False,
        'resource_type': resource_type,
        'title': f'Submit a New {resource_type.capitalize()}',
        'categories': Category.objects.all(),
        'article_form': article_form,
        'book_form': book_form,
        'course_form': course_form,
    }

    return render(request, 'resources/resources_form.html', context)


@login_required
def resource_update(request, resource_slug):
    """
    View for editing an existing resource.
    """
    # 1. Identify the resource and its type
    resource = None
    resource_type = None

    # Try to find the resource across all models
    for model in [Book, Article, Course]:
        try:
            found_resource = model.objects.get(slug=resource_slug, author=request.user)
            resource = found_resource
            resource_type = resource.get_resource_type().lower()
            break
        except model.DoesNotExist:
            continue

    if not resource:
        messages.error(request, 'Resource not found or you are not the author.')
        raise Http404("Resource not found or user not authorized to edit.")

    # 2. Get the correct form class
    form_map = {
        'book': BookForm,
        'article': ArticleForm,
        'course': CourseForm,
    }

    ResourceFormClass = form_map.get(resource_type)

    if not ResourceFormClass:
        messages.error(request, f"Invalid resource type: {resource_type}")
        return redirect('resource_list')

    if request.method == 'POST':
        form = ResourceFormClass(request.POST, request.FILES, instance=resource)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Set is_approved back to False upon major update
                    resource = form.save(commit=False)
                    resource.is_approved = False

                    # For courses, clear existing roadmap since content changed
                    if isinstance(resource, Course):
                        resource.roadmap_json = None

                    resource.save()
                    form.save_m2m()

                messages.success(request,
                                 f'{resource_type.capitalize()} updated successfully! Awaiting admin re-approval.')
                return redirect('resource_detail', resource_slug=resource.slug)

            except Exception as e:
                logger.error(f"Error updating {resource_type}: {str(e)}")
                messages.error(request, f'Error updating resource: {str(e)}')
        else:
            messages.error(request, 'Please correct the form errors.')
    else:
        form = ResourceFormClass(instance=resource)

    context = {
        'form': form,
        'edit_mode': True,
        'resource_type': resource_type,
        'resource': resource,
        'title': f'Edit {resource_type.capitalize()}',
        'categories': Category.objects.all(),
    }

    return render(request, 'resources/resources_form.html', context)


@require_POST
@login_required
def resource_interaction(request):
    """
    Handles user interactions (upvote, save, complete) with resources.
    """
    try:
        resource_id = request.POST.get('resource_id')
        interaction_type = request.POST.get('interaction_type')

        if not resource_id or not interaction_type:
            return JsonResponse({
                'success': False,
                'error': 'Missing resource_id or interaction_type'
            }, status=400)

        # Find which resource type this is
        resource = None
        resource_model = None

        for model in [Book, Article, Course]:
            try:
                found_resource = model.objects.get(pk=resource_id, is_approved=True)
                resource = found_resource
                resource_model = model
                break
            except model.DoesNotExist:
                continue

        if not resource:
            return JsonResponse({
                'success': False,
                'error': 'Resource not found'
            }, status=404)

        # Get or create UserResourceInteraction
        content_type = ContentType.objects.get_for_model(resource_model)

        user_interaction, created = UserResourceInteraction.objects.get_or_create(
            user=request.user,
            content_type=content_type,
            object_id=resource.pk,
            defaults={
                'upvoted': False,
                'saved': False,
                'completed': False
            }
        )

        # Toggle the interaction
        new_state = False
        if interaction_type == 'upvote':
            new_state = not user_interaction.upvoted
            user_interaction.upvoted = new_state

            # Update resource upvote count
            if new_state:
                resource.upvote_count += 1
            else:
                resource.upvote_count = max(0, resource.upvote_count - 1)

        elif interaction_type == 'save':
            new_state = not user_interaction.saved
            user_interaction.saved = new_state

            # Update resource saved count
            if new_state:
                resource.saved_count += 1
            else:
                resource.saved_count = max(0, resource.saved_count - 1)

        elif interaction_type == 'complete':
            new_state = not user_interaction.completed
            user_interaction.completed = new_state

        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid interaction type'
            }, status=400)

        # Save changes
        user_interaction.save()
        resource.save()

        # Return success response
        return JsonResponse({
            'success': True,
            'interaction_type': interaction_type,
            'new_state': new_state,
            'upvote_count': resource.upvote_count,
            'saved_count': resource.saved_count,
            'completed': user_interaction.completed
        })

    except Exception as e:
        logger.error(f"Error in resource_interaction: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_POST
@login_required
def add_comment(request, resource_slug):
    """
    Handles POST requests for adding a comment to a resource.
    """
    try:
        # Find the concrete resource instance
        resource = None
        for model in [Book, Article, Course]:
            try:
                found_resource = model.objects.get(slug=resource_slug, is_approved=True)
                resource = found_resource
                break
            except model.DoesNotExist:
                continue
        if not resource:
            raise Http404("Resource not found or not approved")

    except Http404:
        messages.error(request, 'Resource not found or not approved')
        return redirect('resource_list')

    content = request.POST.get('content', '').strip()

    if content:
        # Create the comment
        Comment.objects.create(
            resource=resource,
            author=request.user,
            content=content,
        )
        messages.success(request, 'Comment added successfully')
    else:
        messages.error(request, 'Comment cannot be empty.')

    return redirect('resource_detail', resource_slug=resource_slug)


@login_required
@require_POST
def course_enroll(request, course_id):
    """
    Enrolls a user in a course and creates learning goals
    """
    logger.info(f"User {request.user.id} attempting enrollment in Course {course_id}")

    course = get_object_or_404(Course, id=course_id)

    try:
        with transaction.atomic():
            # 1. Create LearningGoal and Milestones
            goal = enroll_user_in_course(request.user, course)
            logger.info(f"Goal {goal.id} created for course {course.id}")

            # 2. Track concrete enrollment
            progress, created = CourseProgress.objects.get_or_create(
                user=request.user,
                course=course
            )

            if created:
                messages.success(request, f"You are now enrolled in {course.title}!")
                logger.info(f"CourseProgress created for user {request.user.id}")
            else:
                messages.info(request, f"You are already enrolled in {course.title}")
                logger.info(f"User {request.user.id} already had CourseProgress")

    except Exception as e:
        logger.error(f"Enrollment Error: {str(e)}")
        messages.error(request, f"There was an error setting up your tracking: {str(e)}")

    return redirect('resource_detail', resource_slug=course.slug)


@login_required
def update_module_progress(request):
    """
    Updates module progress and learning statistics
    """
    try:
        module_id = request.POST.get('module_id')
        course_id = request.POST.get('course_id')
        seconds_watched = int(request.POST.get('seconds', 0))

        if not module_id or not course_id:
            return JsonResponse({'status': 'error', 'message': 'Missing module_id or course_id'}, status=400)

        progress = get_object_or_404(CourseProgress, user=request.user, course_id=course_id)
        mod_state, _ = ModuleProgress.objects.get_or_create(
            course_progress=progress,
            module_id=module_id,
            user=request.user
        )

        # Update time spent
        mod_state.time_spent += timedelta(seconds=seconds_watched)

        # Logic for completion
        if request.POST.get('completed') == 'true':
            mod_state.is_completed = True
            mod_state.completed_at = timezone.now()

            # Update User Stats
            stats, _ = UserLearningStats.objects.get_or_create(user=request.user)
            stats.update_streak()
            stats.total_modules_completed += 1
            stats.total_learning_time += mod_state.time_spent
            stats.save()

        mod_state.save()

        return JsonResponse({
            'status': 'success',
            'time_spent': str(mod_state.time_spent),
            'is_completed': mod_state.is_completed
        })

    except Exception as e:
        logger.error(f"Error in update_module_progress: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@login_required
def generate_course_ajax(request):
    """
    AJAX endpoint for generating course content
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        title = data.get('title')
        description = data.get('description')
        difficulty = data.get('difficulty', 'B')

        if not title or not description:
            return JsonResponse({'error': 'Title and description are required'}, status=400)

        # Create a temporary course object
        from .models import Course
        temp_course = Course(
            title=title,
            description=description,
            difficulty=difficulty,
            author=request.user
        )

        # Generate roadmap
        from .course_tools import generate_course_roadmap
        structured_modules = generate_course_roadmap(temp_course)

        # Calculate totals
        total_seconds = sum(module.get('duration_seconds', 0) for module in structured_modules)
        total_videos = sum(len(module.get('videos', [])) for module in structured_modules)

        # Format duration for display
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            total_duration = f"{hours}h {minutes}m"
        else:
            total_duration = f"{minutes}m"

        # Generate difficulty progression
        difficulty_progression = generate_difficulty_progression(difficulty)

        return JsonResponse({
            'success': True,
            'improved_title': temp_course.title,
            'enriched_description': temp_course.description,
            'difficulty': difficulty,
            'difficulty_progression': difficulty_progression,
            'structured_modules': structured_modules,
            'total_seconds': total_seconds,
            'total_duration': total_duration,
            'total_videos': total_videos,
            'total_modules': len(structured_modules)
        })

    except Exception as e:
        logger.error(f"Error in generate_course_ajax: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def generate_difficulty_progression(difficulty):
    """
    Generate a human-readable difficulty progression message
    """
    progressions = {
        'B': "This course is perfect for beginners with no prior experience",
        'I': "This course will take you from beginner to intermediate level",
        'A': "This advanced course builds upon intermediate knowledge to reach expert level"
    }
    return progressions.get(difficulty, "This course offers comprehensive learning at your level")


@login_required
@require_http_methods(["POST"])
def regenerate_course_roadmap(request, course_id):
    """
    Regenerates the course roadmap using AI.
    Only course creator or admin can regenerate.
    """
    try:
        # Get the course
        course = get_object_or_404(Course, id=course_id)

        # Check permissions
        if not (request.user == course.author or request.user.is_staff):
            messages.error(request, "You don't have permission to regenerate this course roadmap.")
            return redirect('resource_detail', resource_slug=course.slug)

        # Check if regeneration is allowed (rate limiting)
        cache_key = f"regenerate_cooldown_{course_id}_{request.user.id}"
        if cache.get(cache_key):
            messages.warning(request, "Please wait a few minutes before regenerating again.")
            return redirect('resource_detail', resource_slug=course.slug)

        # Set cooldown (5 minutes)
        cache.set(cache_key, True, 300)

        with transaction.atomic():
            # Clear existing roadmap
            course.roadmap_json = None
            course.estimated_duration = None
            course.difficulty_progression = None
            course.save()

            # Regenerate roadmap
            try:
                structured_modules = generate_course_roadmap(course)

                # Update course with new data
                course.refresh_from_db()

                # Calculate new totals
                total_seconds = sum(module.get('duration_seconds', 0) for module in structured_modules)
                total_videos = sum(len(module.get('videos', [])) for module in structured_modules)

                # Generate difficulty progression if not present
                if not course.difficulty_progression:
                    difficulty_progression = generate_difficulty_progression(course.difficulty)
                    course.difficulty_progression = difficulty_progression
                    course.save()

                messages.success(
                    request,
                    f"Course roadmap regenerated successfully! Found {total_videos} videos across {len(structured_modules)} modules."
                )
                logger.info(f"Course {course_id} roadmap regenerated by user {request.user.id}")

            except Exception as e:
                logger.error(f"Error regenerating roadmap for course {course_id}: {str(e)}")
                messages.error(
                    request,
                    "Failed to regenerate roadmap. Please check your API keys or try again later."
                )

        return redirect('resource_detail', resource_slug=course.slug)

    except Exception as e:
        logger.error(f"Error in regenerate_course_roadmap: {str(e)}")
        messages.error(request, "An unexpected error occurred.")
        return redirect('resource_list')


# Also add this helper function if not already present:
def generate_difficulty_progression(difficulty):
    """
    Generate a human-readable difficulty progression message
    """
    progressions = {
        'B': "Perfect for absolute beginners with no prior experience",
        'I': "Takes you from basic understanding to intermediate proficiency",
        'A': "Transforms intermediate knowledge into advanced expertise"
    }
    return progressions.get(difficulty, "Comprehensive learning path for your skill level")


# Add a view to view course progress analytics:
@login_required
def course_analytics(request, course_id):
    """
    Shows analytics for a course (creator/admin only)
    """
    course = get_object_or_404(Course, id=course_id)

    # Check permissions
    if not (request.user == course.author or request.user.is_staff):
        messages.error(request, "You don't have permission to view analytics for this course.")
        return redirect('resource_detail', resource_slug=course.slug)

    # Get enrollment statistics
    total_enrollments = CourseProgress.objects.filter(course=course).count()
    completed_enrollments = CourseProgress.objects.filter(course=course, completed=True).count()

    # Get module completion rates
    module_stats = []
    if course.roadmap_json:
        roadmap = json.loads(course.roadmap_json)
        for i, module in enumerate(roadmap, 1):
            module_completions = ModuleProgress.objects.filter(
                course_progress__course=course,
                module_id=i,
                is_completed=True
            ).count()

            completion_rate = 0
            if total_enrollments > 0:
                completion_rate = (module_completions / total_enrollments) * 100

            module_stats.append({
                'module_number': i,
                'module_title': module.get('title', f'Module {i}'),
                'total_completions': module_completions,
                'completion_rate': round(completion_rate, 1),
                'video_count': len(module.get('videos', []))
            })

    # Get recent activity
    recent_completions = ModuleProgress.objects.filter(
        course_progress__course=course,
        is_completed=True
    ).select_related('user', 'course_progress').order_by('-completed_at')[:10]

    context = {
        'course': course,
        'total_enrollments': total_enrollments,
        'completed_enrollments': completed_enrollments,
        'completion_rate': round((completed_enrollments / total_enrollments * 100) if total_enrollments > 0 else 0, 1),
        'module_stats': module_stats,
        'recent_completions': recent_completions,
        'total_modules': len(module_stats),
        'avg_completion_rate': round(
            sum(stat['completion_rate'] for stat in module_stats) / len(module_stats) if module_stats else 0,
            1
        )
    }

    return render(request, 'resources/course_analytics.html', context)