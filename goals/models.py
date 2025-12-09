# learnhub/goals/models.py
from django.db import models
from django.conf import settings
from django.template.defaultfilters import slugify
from django.utils import timezone
from django.db.models import Count, Q


# 1. Learning Goal Model (The Parent)
class LearningGoal(models.Model):
    """
    The main objective set by the user (Kanban card).
    """
    STATUS_CHOICES = [
        ('N', 'Not Started'),
        ('I', 'In Progress'),
        ('C', 'Completed'),
        ('A', 'Archived'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learning_goals'
    )
    title = models.CharField(max_length=150)
    slug = models.SlugField(unique=True, max_length=150)
    description = models.TextField(blank=True)

    # Kanban State
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='N')

    # Dates
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Progress (Computed in views/signals)
    milestone_count = models.IntegerField(default=0)
    milestone_completed_count = models.IntegerField(default=0)

    class Meta:
        ordering = ('status', '-created_at')
        unique_together = ('user', 'slug')

    def save(self, *args, **kwargs):
        if not self.slug:
            # Create a unique slug based on title and user
            base_slug = slugify(self.title)
            unique_slug = base_slug
            num = 1
            while LearningGoal.objects.filter(user=self.user, slug=unique_slug).exists():
                unique_slug = f'{base_slug}-{num}'
                num += 1
            self.slug = unique_slug

        # Set completed_at date if status changes to Completed
        if self.pk and self.status == 'C' and not self.completed_at:
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.title} ({self.get_status_display()})'

    @property
    def progress_percentage(self):
        """Calculates the completion percentage based on milestones."""
        if self.milestone_count == 0:
            return 0
        return int((self.milestone_completed_count / self.milestone_count) * 100)

    #New method recalculates and saves progress counters
    def update_progress_counters(self):
        """Aggregates and updates the milestone  counts on the goal"""

        #Calculate total count and completed count directly from the related milestones
        agg_data = self.milestones.aggregate(
            total=Count('id'),
            completed=Count('id', filter=models.Q(is_completed=True)),
        )

        self.milestone_count = agg_data['total']
        self.milestone_completed_count = agg_data['completed']


        #Check if the goal should be auto-completed or marked in progress
        if self.milestone_count > 0 and self.milestone_count == self.milestone_completed_count:
            # if all the milestones are done , Mark the goal as completed
            if self.status != 'C':
                self.status = 'C'
            elif self.milestone_completed_count > 0:
                #if some milestones are done , ensure the status is in progress
                if self.status == 'N':
                    self.status = 'I'


            #Save only the counter fields and status
            self.save(update_fields=[
                'milestone_count',
                'milestone_completed_count',
                'status',
                'completed_at'
            ])


# 2. Goal Milestone Model (The Checklist Item)
class GoalMilestone(models.Model):
    """
    A specific, measurable step within a learning goal.
    """
    goal = models.ForeignKey(
        LearningGoal,
        on_delete=models.CASCADE,
        related_name='milestones'
    )
    title = models.CharField(max_length=150)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('created_at',)

    def save(self, *args, **kwargs):
        # Set completion date if status changes to completed
        if self.pk and self.is_completed and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.pk and not self.is_completed:
            self.completed_at = None

        super().save(*args, **kwargs)


        #Trigger a process update: Update parent goal counter after saving
        self.goal.update_progress_counters() #call the new method

    def __str__(self):
        return self.title


# 3. Goal Update Model (The Journal/Timeline)
class GoalUpdate(models.Model):
    """
    A journal entry or log of progress made towards a goal.
    """
    goal = models.ForeignKey(
        LearningGoal,
        on_delete=models.CASCADE,
        related_name='updates'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='goal_updates'
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional: Link to a resource if the update is about completing/using a specific resource
    resource = models.ForeignKey(
        'resources.Resource',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='goal_updates'
    )

    class Meta:
        ordering = ('-created_at',)
        verbose_name = "Goal Update"
        verbose_name_plural = "Goal Updates"

    def __str__(self):
        return f'Update for {self.goal.title} on {self.created_at.date()}'