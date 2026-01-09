from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from goals.models import LearningGoal, GoalMilestone
from resources.models import CourseProgress

@transaction.atomic
def enroll_user_in_course(user, course):
    # 1. Fetch Roadmap
    roadmap = course.get_roadmap()

    # 2. Create LearningGoal
    course_type = ContentType.objects.get_for_model(course)
    goal = LearningGoal.objects.create(
        user=user,
        title=f"Learning: {course.title}",
        status='I',
        content_type=course_type,
        object_id=course.id
    )

    # 3. Create Milestones from Roadmap videos
    if roadmap:
        for module in roadmap:
            for video in module.get('videos', []):
                GoalMilestone.objects.create(
                    goal=goal,
                    title=video['title'],
                    is_completed=False
                )
    return goal

@transaction.atomic
def update_learning_progress(user, course, video_title, time_spent_seconds):
    """
    Updates progress metrics, checks for completion, and archives goals.
    """
    # 1. Update the Milestone
    goal = LearningGoal.objects.get(
        user=user,
        object_id=course.id,
        content_type=ContentType.objects.get_for_model(course)
    )
    milestone = goal.milestones.filter(title=video_title).first()

    if milestone and not milestone.is_completed:
        milestone.is_completed = True
        milestone.completed_at = timezone.now()
        milestone.save()

    # 2. Update User Stats (Time & Streaks)
    profile = user.profile
    profile.total_hours_learned += (time_spent_seconds / 3600)
    profile.update_streak()  # Method to handle consecutive days
    profile.save()

    # 3. Check for Course Completion
    total = goal.milestones.count()
    completed = goal.milestones.filter(is_completed=True).count()

    if completed >= total:
        finalize_course_completion(user, goal, course)


@transaction.atomic
def finalize_course_completion(user_progress):
    """
    Standardizes the cascading effects of finishing a course.
    Wrapped in a transaction to ensure all updates succeed or fail together.
    """
    # 1. Prevent redundant processing
    if user_progress.completed:
        return

    # 2. Update Resource Progress
    user_progress.completed = True
    user_progress.last_accessed = timezone.now()
    user_progress.save()

    # 3. Archive Corresponding LearningGoals
    # We target uncompleted goals for this specific user and category
    LearningGoal.objects.filter(
        user=user_progress.user,
        category=user_progress.course.category,
        completed=False
    ).update(
        completed=True,
        status='C'  # 'C' for Completed
    )

    # 4. Update User Profile Metrics
    profile = user_progress.user.profile
    if hasattr(profile, 'increment_completed_resources'):
        profile.increment_completed_resources()
