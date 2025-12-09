from unicodedata import category

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Count, Q, Case, When, BooleanField, IntegerField, F, Value  # Q is for complex lookups
from django.contrib import messages
from django.conf import settings
from django.db import models, transaction
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST



from .models import Resource, Tag, UserResourceInteraction, Comment
from core.models import Category
from .forms import ResourceForm
import logging


logger = logging.getLogger(__name__)






@login_required(login_url='login')
def resource_list(request):
    # 1.Base Queryset : Only approved resources, optimized data fetching
    queryset = Resource.objects.filter(is_approved=True).select_related('author', 'category').prefetch_related('tags')

    # 2 add annotations for Sorting /Stats
    # Note: Remove 'views' field if it doesn't exist in your model
    queryset = queryset.annotate(
        comment_count=Count('comments', distinct=True),
        # Simple popularity score (remove 'views' if field doesn't exist)
        popularity=Case(
            When(upvote_count__gt=0, then=(F('upvote_count') + F('comment_count') * 2)),
            # If you add views later: then=(F('upvote_count') + F('comment_count') * 2 + F('views') * 0.1)
            default=0,
            output_field=IntegerField()
        )
    )

    # 3 Filtering logic(Based on Url Parameters)
    category_slug = request.GET.get('category')
    difficulty = request.GET.get('difficulty')
    q = request.GET.get('q')  # search query

    if category_slug:
        queryset = queryset.filter(category__slug=category_slug)

    if difficulty and difficulty in ['B', 'I', 'A']:
        queryset = queryset.filter(difficulty=difficulty)

    if q:
        queryset = queryset.filter(
            Q(title__icontains=q) |
            Q(description__icontains=q) |
            Q(tags__name__icontains=q)
        ).distinct()

    # 4 Sorting
    sort_by = request.GET.get('sort', 'newest')  # Default to the newest

    if sort_by == 'popular':
        queryset = queryset.order_by('-popularity', '-created_at')
    elif sort_by == 'upvotes':
        queryset = queryset.order_by('-upvote_count', '-created_at')
    elif sort_by == 'comments':
        queryset = queryset.order_by('-comment_count', '-created_at')
    else:  # 'newest'
        # If you don't have a views field, just sort by created_at
        queryset = queryset.order_by('-created_at')
        # If you add views later: queryset.order_by('-views', '-created_at')

    # 5 User interaction Annotation (for logged in users)
    if request.user.is_authenticated:
        queryset = queryset.annotate(
            is_upvoted=Case(
                When(interactions__user=request.user, interactions__upvoted=True, then=True),
                default=False,
                output_field=BooleanField()
            ),
            is_saved=Case(
                When(interactions__user=request.user, interactions__saved=True, then=True),
                default=False,
                output_field=BooleanField()
            )
        )
    else:
        queryset = queryset.annotate(
            is_upvoted=Value(False, output_field=BooleanField()),
            is_saved=Value(False, output_field=BooleanField()),
        )

    # 6 Pagination
    page_number = request.GET.get('page', 1)
    paginator = Paginator(queryset, 12)  # Show 12 resources per page

    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    # Get filters/metadata for the sidebar
    categories = Category.objects.all().annotate(count=Count('resources')).order_by('-count')
    tags = Tag.objects.annotate(count=Count('resources')).order_by('-count')[:20]

    context = {
        'page_obj': page_obj,
        'resources': page_obj.object_list,
        'categories': categories,
        'tags': tags,
        'current_sort': sort_by,
        'current_query': q or '',
    }
    return render(request, 'resources/resource_list.html', context)


#2 Resource Detail View
def resource_detail(request, resource_slug):
    # Debug logging
    print(f"Looking for resource with slug: {resource_slug}")

    try:
        resource = Resource.objects.get(
            slug=resource_slug,
            is_approved=True
        )
        print(f"Found resource: {resource.title}")
    except Resource.DoesNotExist:
        print(f"No resource found with slug: {resource_slug}")
        # List all slugs for debugging
        all_slugs = Resource.objects.values_list('slug', flat=True)
        print(f"Available slugs: {list(all_slugs)}")
        raise

    #Get the comments, prefetching the author of each comment
    comments = resource.comments.filter(
        parent__isnull=True
    ).select_related('author').order_by('-created_at')


    #Get the user interaction status if the user is logged in
    user_interaction = None
    if request.user.is_authenticated:
        user_interaction = UserResourceInteraction.objects.filter(
            user=request.user, resource=resource
        ).first()

    #Determine if the current user is the creator ( for edting)
    user_is_creator = request.user.is_authenticated and request.user == resource.author

    # Calculate a simple average rating (for future implementation)
    # average_rating = resource.comments.aggregate(avg_rating=models.Avg('rating'))['avg_rating']

    # Placeholder for Similar Resources (will be implemented in Phase 7 - Recommendations)
    similar_resources = Resource.objects.filter(
        category=resource.category
    ).exclude(pk=resource.pk).order_by('?')[:3]


    #Fetched related data (comments ,similar resources, user interaction)

    context = {
        'resource': resource,
        'comments': comments,
        'user_interaction': user_interaction,
        'user_is_creator': user_is_creator,
        'similar_resources': similar_resources,
    }

    return render (request, 'resources/resources_detail.html', context)

#3 Resource Creation View

@login_required
def resource_create(request):
    """
    View for creating new resources with proper error handling
    """
    # Verify user exists in database using your custom user model
    if request.user.is_authenticated:
        from core.models import CustomUser  # Import your custom user model

        try:
            # Try to get the user from database
            db_user = CustomUser.objects.get(id=request.user.id)
            print(f"DEBUG: User verified in DB: {db_user.email}")
        except CustomUser.DoesNotExist:
            # User doesn't exist in DB - clear session
            print(f"DEBUG: ERROR: User ID {request.user.id} not in database!")
            from django.contrib.auth import logout
            logout(request)
            messages.error(request, 'Your session is invalid. Please log in again.')
            return redirect('login')  # Adjust to your login URL


    if request.method == 'POST':
        print(f"DEBUG: POST data received")
        print(f"DEBUG: POST keys: {list(request.POST.keys())}")

        form = ResourceForm(request.POST)
        print(f"DEBUG: Form created. Is bound: {form.is_bound}")
        print(f"DEBUG: Form data: {form.data if hasattr(form, 'data') else 'No data'}")

        if form.is_valid():
            print(f"DEBUG: Form is valid!")
            print(f"DEBUG: Cleaned data: {form.cleaned_data}")

            try:
                resource = form.save(commit=False)
                print(f"DEBUG: Resource instance created: {resource}")

                resource.author = request.user
                print(f"DEBUG: Author set to: {resource.author}")

                resource.save()
                print(f"DEBUG: Resource saved to database. ID: {resource.id}")

                form.save_m2m()
                print(f"DEBUG: M2M relationships saved")

                logger.info(f"Resource created: {resource.title} by {request.user.email}")
                messages.success(request, 'Resource created successfully! Awaiting approval')
                print(f"DEBUG: Success message set")

                return redirect('resource_detail', resource_slug=resource.slug)

            except Exception as e:
                print(f"DEBUG: Exception occurred: {str(e)}")
                import traceback
                traceback.print_exc()
                logger.error(f"Error creating resource: {str(e)}")
                messages.error(request, f'Error creating resource: {str(e)}')
        else:
            print(f"DEBUG: Form is NOT valid")
            print(f"DEBUG: Form errors: {form.errors.as_json()}")
            logger.warning(f"Form validation errors: {form.errors}")
            messages.error(request, 'Please correct the errors below.')
    else:
        print(f"DEBUG: GET request, creating empty form")
        form = ResourceForm()

    context = {
        'form': form,
        'edit_mode': False,
        'categories': Category.objects.all(),
    }

    print(f"DEBUG: Rendering template with context")
    return render(request, 'resources/resources_form.html', context)



def resource_interaction(request):
    """
    Handles Ajax requests for upvoting and saving resources
    Requires : resource_id (int) , action (str: 'upvote' or 'save'), type( str: 'toggle')

    :param request:
    :return:
    """

    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': "Authentication required"
        })

    try :
        resource_id = request.POST.get('resource_id')
        action = request.POST.get('action')

        resource = get_object_or_404(Resource, pk=resource_id)

    except (Resource.DoesNotExist, ValueError):
        return JsonResponse({
            'success': False,
            'error': "Invalid resource ID"
        })

    #Find or create the interaction record for this user/resource
    interaction, created = UserResourceInteraction.objects.get_or_create(
        user=request.user,
        resource=resource,
        #Default values for creation are false , which is fine
    )

    is_active = False  #Tracks the final state of the interaction


    if action == 'upvote':
        #Toggle upvote status
        interaction.upvoted = not interaction.upvoted
        interaction.save()
        is_active =  interaction.upvoted

        #updated cached count on the Resource model
        if is_active:
            resource.upvote_count = models.F('upvote_count') + 1
        else:
            resource.upvote_count = models.F('upvote_count')  - 1


        resource.save(update_fields=['upvote_count'])

        #Refresh the resource object fo get the updated count before returning
        resource.refresh_from_db()

        return JsonResponse({
            'success': True,
            'action': 'upvote',
            'is_active': is_active,
            'new_count': resource.upvote_count,
            'message': f'Resource {"upvoted" if is_active else "unvoted"} successfully. ',
        })

    elif action == 'save':
        #toggle the save status
        interaction.saved = not interaction.saved
        interaction.save()
        is_active = interaction.saved

        #update cached count on the resource model
        if is_active:
            resource.saved_count = models.F('saved_count') + 1
        else:
            resource.saved_count = models.F('saved_count') - 1

        resource.save(update_fields=['saved_count'])
        resource.refresh_from_db()

        return JsonResponse({
            'success': True,
            'action': 'save',
            'is_active': is_active,
            'new_count': resource.saved_count,
            'message': f'Resource {"saved" if is_active else "unsaved"} successfully. ',
        })
    return HttpResponseBadRequest('Invalid action')




