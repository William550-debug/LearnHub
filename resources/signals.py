from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ModuleProgress
from .services import finalize_course_completion


@receiver(post_save, sender=ModuleProgress)
def handle_module_completion(sender, instance, created, **kwargs):
    """
    Signal receiver that triggers every time a ModuleProgress record is saved.
    It checks if the specific module was marked as completed and then
    delegates the course-wide completion logic to the service layer.
    """
    # 1. Only proceed if the module has just been marked as completed
    # We check instance.is_completed to ensure we don't run this for mid-video updates
    if instance.is_completed:
        user_progress = instance.course_progress
        course = user_progress.course

        # 2. Get the total steps required for this specific course
        # It is better to store this on the Course model than using a global constant
        total_steps_required = course.total_steps if hasattr(course, 'total_steps') else 10

        # 3. Count how many modules the user has actually finished
        completed_count = user_progress.module_states.filter(is_completed=True).count()

        # 4. If the requirement is met, trigger the Service Layer
        # This keeps business logic (like archiving goals) in services.py
        if completed_count >= total_steps_required and not user_progress.completed:
            finalize_course_completion(user_progress)