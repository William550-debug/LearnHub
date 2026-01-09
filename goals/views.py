# learnhub/goals/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Prefetch, Q
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.db import transaction

from .models import LearningGoal, GoalMilestone, GoalUpdate
from .forms import LearningGoalForm


@login_required
def goal_list(request):
    """
    Displays the Kanban board view of all user goals, grouped by status.
    This view now serves as the primary Goal Dashboard.
    """
    # Optimized query: Fetch all goals and prefetch all related milestones
    goals = LearningGoal.objects.filter(user=request.user).prefetch_related(
        Prefetch('milestones', queryset=GoalMilestone.objects.order_by('created_at')),
        # Prefetch related resources used in goal updates, if any
        Prefetch('updates__resource')
    )

    # Group goals by status for the Kanban display
    kanban_columns = {
        'Not Started': goals.filter(status='N'),
        'In Progress': goals.filter(status='I'),
        'Completed': goals.filter(status='C'),
        'Archived': goals.filter(status='A'),
    }

    # Form for adding a new goal (displayed in a modal/sidebar)
    new_goal_form = LearningGoalForm()

    # Calculate basic stats for the goals.html template display
    total_goals = goals.count()
    completed_goals = goals.filter(status='C').count()
    active_goals = goals.filter(status__in=['N', 'I']).count()

    # Simple overdue calculation (goals not completed and past due date)
    overdue_goals = goals.filter(status__in=['N', 'I'], due_date__lt=timezone.now().date()).count()

    completion_rate = (completed_goals / total_goals * 100) if total_goals > 0 else 0

    context = {
        'kanban_columns': kanban_columns,
        'goals': goals,  # Pass the entire queryset for flexible template use
        'new_goal_form': new_goal_form,
        'status_choices': LearningGoal.STATUS_CHOICES,
        'stats': {
            'total_goals': total_goals,
            'completed_goals': completed_goals,
            'active_goals': active_goals,
            'overdue_goals': overdue_goals,
            'completion_rate': int(completion_rate),
        }
    }
    return render(request, 'goals/goal_list.html', context)


@login_required
@require_POST
def goal_create(request):
    """
    Handles the creation of a new learning goal via POST request (usually from a modal).
    """
    form = LearningGoalForm(request.POST)

    if form.is_valid():
        goal = form.save(commit=False)
        goal.user = request.user

        # Ensure the goal starts as 'Not Started' unless explicitly set otherwise
        if not goal.status:
            goal.status = 'N'

        goal.save()
        messages.success(request, f'Goal "{goal.title}" created successfully!')
        # Redirect to the goal list, which will reload the Kanban board
        return redirect('goal_list')
    else:
        # If form fails, use the message system to flash errors on redirect
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"Error in {field}: {error}")
        return redirect('goal_list')


@require_POST
@login_required
@transaction.atomic
def milestone_toggle(request, milestone_pk):
    """
    Handles AJAX POST to toggle the completion status of a GoalMilestone.
    """
    try:
        milestone = get_object_or_404(GoalMilestone, pk=milestone_pk, goal__user=request.user)

        # Toggle the status
        milestone.is_completed = not milestone.is_completed
        # The save method automatically updates the parent goal's counters
        milestone.save()

        # Refresh the parent goal to send back the latest progress data
        goal = milestone.goal
        goal.refresh_from_db()

        return JsonResponse({
            'success': True,
            'is_completed': milestone.is_completed,
            'goal_id': goal.pk,
            'progress_percent': goal.progress_percentage,
            'milestone_completed_count': goal.milestone_completed_count,
            'goal_status': goal.get_status_display(),
            'goal_status_code': goal.status,
        })

    except LearningGoal.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Milestone not found or unauthorized.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_POST
@login_required
def goal_update_status(request, goal_pk):
    """
    Handles AJAX POST to update the Kanban status of a LearningGoal (for drag-and-drop support).
    Requires: new_status (str: 'N', 'I', 'C', 'A').
    """
    new_status = request.POST.get('new_status')

    # Validate the incoming status code
    valid_status_codes = [choice[0] for choice in LearningGoal.STATUS_CHOICES]
    if new_status not in valid_status_codes:
        return HttpResponseBadRequest('Invalid status code provided.')

    try:
        goal = get_object_or_404(LearningGoal, pk=goal_pk, user=request.user)

        # Only allow status change if it's different
        if goal.status != new_status:
            goal.status = new_status

            # Update completed_at field if status is changing to or from 'Completed'
            if new_status == 'C':
                goal.completed_at = timezone.now()
            elif goal.status != 'C' and goal.completed_at is not None:
                goal.completed_at = None

            goal.save(update_fields=['status', 'completed_at'])

            return JsonResponse({
                'success': True,
                'goal_id': goal.pk,
                'new_status': goal.get_status_display(),
                'new_status_code': goal.status,
            })

    except LearningGoal.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Goal not found or unauthorized.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


