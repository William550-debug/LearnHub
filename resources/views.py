from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Count, Q, Case, When, BooleanField, IntegerField, F, Value
from django.db import transaction
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest, Http404
import logging

from django.views.decorators.http import require_POST

# Import all concrete models and the base model
from .models import BaseResource, Book, Article, Course, Tag, UserResourceInteraction, Comment, CourseProgress
from core.models import Category
# Import all new forms
from .forms import BookForm, ArticleForm, CourseForm
# Import the new helper files
from .course_tools import generate_course_roadmap
from .mixins import get_concrete_resource_type
from django.contrib.contenttypes.models import ContentType


logger = logging.getLogger(__name__)

# --- 1. Resource List View (Cleaned) ---
@login_required(login_url='login')
def resource_list(request):
    # 1. Gather PKs from all concrete models since BaseResource is abstract
    book_pks = Book.objects.filter(is_approved=True).values_list('pk', flat=True)
    article_pks = Article.objects.filter(is_approved=True).values_list('pk', flat=True)
    course_pks = Course.objects.filter(is_approved=True).values_list('pk', flat=True)

    all_pks = list(book_pks) + list(article_pks) + list(course_pks)

    # 2. Query the concrete 'Article' model using the combined ID list
    queryset = Article.objects.filter(pk__in=all_pks).select_related(
        'author', 'category'
    ).prefetch_related('tags')

    # 3. Annotate using the correct 'interactions' keyword from models.py
    if request.user.is_authenticated:
        queryset = queryset.annotate(
            comment_count=Count('comments', distinct=True),
            is_upvoted=Case(
                When(interactions__user=request.user, interactions__upvoted=True, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            ),
            is_saved=Case(
                When(interactions__user=request.user, interactions__saved=True, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            )
        )

    # 4. Sorting & Pagination
    sort_by = request.GET.get('sort', 'newest')
    # ... sorting logic ...

    paginator = Paginator(queryset, 12)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'resources/resource_list.html', {
        'page_obj': page_obj,
        'resources': page_obj.object_list,
        'categories': Category.objects.all(),
    })

# --- 2. Resource Detail View (Cleaned) ---
def resource_detail(request, resource_slug):
    """
    Displays the detail page for any concrete resource type (Book, Article, Course).
    It uses the slug to find the correct resource across all models.
    """
    try:
        # Find the resource using the slug across all concrete types.
        resource = None
        for model in [Book, Article, Course]:
            try:
                found_resource = model.objects.get(slug=resource_slug, is_approved=True)
                resource = found_resource
                break
            except model.DoesNotExist:
                continue

        if not resource:
            raise Http404("Resource not found or not approved.")

    except Http404:
        raise

    # Get the ContentType for the specific resource instance

    resource_content_type = ContentType.objects.get_for_model(resource)

    # Get the comments, prefetching the author
    comments = Comment.objects.filter(
        content_type=resource_content_type,
        object_id=resource.pk,
        parent__isnull=True
    ).select_related('author').order_by('-created_at')

    # Get the user interaction status
    user_interaction = None
    if request.user.is_authenticated:
        user_interaction_content_type = ContentType.objects.get_for_model(resource.__class__)
        user_interaction = UserResourceInteraction.objects.filter(
            user=request.user,
            content_type=user_interaction_content_type,
            object_id=resource.pk
        ).first()

    user_is_creator = request.user.is_authenticated and request.user == resource.author

    # Course-Specific Logic
    course_roadmap = None
    course_progress = None
    if resource.get_resource_type() == 'Course':
        course_instance = resource
        # Generate the Course Roadmap
        course_roadmap = generate_course_roadmap(course_instance)

        # Track User Progress
        if request.user.is_authenticated:
            course_progress, created = CourseProgress.objects.get_or_create(
                user=request.user, course=course_instance
            )

    # Similar Resources - FIXED: Don't use BaseResource.objects
    similar_resources = []

    # Get resources from other types first
    for model in [Book, Article, Course]:
        if not isinstance(resource, model):
            similar = model.objects.filter(
                category=resource.category,
                is_approved=True
            ).order_by('?')[:2]
            similar_resources.extend(list(similar))

    # If we need more, get from same type
    if len(similar_resources) < 3:
        same_type_resources = resource.__class__.objects.filter(
            category=resource.category,
            is_approved=True
        ).exclude(pk=resource.pk).order_by('?')[:3]
        similar_resources.extend(list(same_type_resources))

    # Randomize and limit to 3
    import random
    random.shuffle(similar_resources)
    similar_resources = similar_resources[:3]

    context = {
        'resource': resource,
        'resource_type': resource.get_resource_type(),
        'comments': comments,
        'user_interaction': user_interaction,
        'user_is_creator': user_is_creator,
        'similar_resources': similar_resources,
        'course_roadmap': course_roadmap,
        'course_progress': course_progress,
    }

    # Use a dynamic template name based on the resource type
    template_name = f'resources/Details/{resource.get_resource_type().lower()}_detail.html'
    return render(request, template_name, context)
# --- 3. Resource Creation View (Cleaned) ---
@login_required
def resource_create(request, resource_type=None):
    """
        View for creating new resources of a specific type (book, article, or course).
        Instantiates all forms for the tabbed interface when in GET mode.
        The resource_type argument can be None initially, but is required for form submission.
    """
    # Use 'article' as a default if resource_type is not provided in the URL initially
    resource_type = resource_type or request.POST.get('resource_type', 'article')

    # Map the URL parameter to the correct Form and Model
    form_map = {
        'book': (BookForm, Book),
        'article': (ArticleForm, Article),
        'course': (CourseForm, Course),
    }

    if resource_type not in form_map:
        messages.error(request, f"Invalid resource type: {resource_type}")
        return redirect('resource_list')

    ResourceFormClass, ResourceModel = form_map[resource_type]

    # Initialize all form variables to None
    article_form, book_form, course_form = None, None, None
    form = None  # This will hold the specific form being processed

    if request.method == 'POST':
        form = ResourceFormClass(request.POST, request.FILES)

        # When a POST fails, we need to re-instantiate the *other* forms for the context
        if resource_type != 'article':
            article_form = ArticleForm()
        if resource_type != 'book':
            book_form = BookForm()
        if resource_type != 'course':
            course_form = CourseForm()

        if form.is_valid():
            try:
                with transaction.atomic():  # Use atomic block for robust transaction
                    # Save the resource instance
                    resource = form.save(commit=False)
                    resource.author = request.user
                    resource.save()
                    # M2M (Tags) are handled in the form's save method
                    form.save_m2m()

                logger.info(f"{resource_type} created: {resource.title} by {request.user.email}")
                messages.success(request,
                                 f'{resource_type.capitalize()} created successfully! Awaiting admin approval.')

                return redirect('resource_detail', resource_slug=resource.slug)

            except Exception as e:  # Catching Exception is acceptable here for transaction rollback
                logger.error(f"Error creating {resource_type}: {str(e)}")
                messages.error(request, f'Error creating resource: An unexpected error occurred.')
        else:
            # ADD THIS FOR DEBUGGING
            print("Form errors:", form.errors.as_json())
            print("Non-field errors:", form.non_field_errors())
            logger.warning(f"{resource_type} form validation errors: {form.errors}")
            messages.error(request, 'Please correct the errors below.')
    else:
        # GET Request: Instantiate all forms for the initial tabbed display
        article_form = ArticleForm()
        book_form = BookForm()
        course_form = CourseForm()
        # Set the 'form' variable to the one matching the URL/default type
        form = form_map[resource_type][0]()

    context = {
        'form': form,  # The specific form instance for the current resource_type
        'edit_mode': False,
        'resource_type': resource_type,
        'title': f'Submit a New {resource_type.capitalize()}',
        'categories': Category.objects.all(),
        # Pass all form instances for the tabbed template logic
        'article_form': article_form,
        'book_form': book_form,
        'course_form': course_form,
    }

    return render(request, 'resources/resources_form.html', context)

@login_required
def resource_update(request, resource_slug):
    """
    View for editing an existing resource.
    Correctly identifies the concrete resource instance and form class.
    """
    # 1. Identify the resource and its type
    resource = None

    # Try to find the resource across all models, ensuring the user is the author
    for model in [Book, Article, Course]:
        try:
            # CORRECTED: Use .get() to fetch the single instance
            found_resource = model.objects.get(slug=resource_slug, author=request.user)
            resource = found_resource
            # CORRECTED: Get the resource type from the instance's method
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
        # Should not happen if get_resource_type() works correctly, but as a safeguard
        messages.error(request, f"Invalid resource type: {resource_type}")
        return redirect('resource_list')

    if request.method == 'POST':
        form = ResourceFormClass(request.POST, request.FILES, instance=resource)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Set is_approved back to False upon major update, requiring re-approval
                    resource = form.save(commit=False)
                    resource.is_approved = False
                    resource.save()
                    form.save_m2m()

                messages.success(request,
                                 f'{resource_type.capitalize()} updated successfully! Awaiting admin re-approval.')
                return redirect('resource_detail', resource_slug=resource.slug)

            except Exception as e:
                logger.error(f"Error updating {resource_type}: {str(e)}")
                messages.error(request, f'Error updating resource: An unexpected error occurred.')
        else:
            messages.error(request, 'Please correct the form errors.')
    else:
        # GET Request: Initialize form with existing instance data
        form = ResourceFormClass(instance=resource)

    context = {
        'form': form,
        'edit_mode': True,
        'resource_type': resource_type,
        'resource': resource,
        'title': f'Edit {resource_type.capitalize()}',
        'categories': Category.objects.all(),
        # In edit mode, we only need the 'form' variable, not all three
    }

    return render(request, 'resources/resources_form.html', context)


@require_POST
@login_required
def resource_interaction(request):
    """
    Handles user interactions (upvote, save, complete) with resources.
    Expects POST data: resource_id, interaction_type ('upvote', 'save', 'complete')
    """
    try:
        # Get data from POST request
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
    :param request:
    :param resource_slug:
    :return:
    """
    try:
        # Step 1 :Find the concrete resource instance
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
        #Create the comment
        #Since Comment used resource_id we can link it directly to BaseResource PK
        Comment.objects.create(
            resource=resource,
            author=request.user,
            content=content,
        )
        messages.success(request, 'Comment added successfully')

    else:
        messages.error(request, 'Comment cannot be empty.')

    return redirect('resource_detail', resource_slug=resource_slug)




# --- 4. Resource Interaction View (Cleaned) ---
# Logic is mostly unchanged, just tidied up variable names.
# ... (rest of resource_interaction function remains similar)

# --- 5. Course Progress View (Cleaned) ---
# Logic is mostly unchanged, just tidied up variable names.
# ... (rest of course_progress_update function remains similar)