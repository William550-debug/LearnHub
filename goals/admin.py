from django.contrib import admin
from .models import LearningGoal, GoalMilestone , GoalUpdate

# Register your models here.

class GoalMilestoneInline(admin.TabularInline):
    model = GoalMilestone
    extra = 1 # show one empty form field


@admin.register(LearningGoal)
class LearningGoalAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'status', 'due_date', 'progress_percentage')
    list_filter = ('status', 'created_at', 'due_date')
    search_fields = ('title', 'description', 'user__email')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [GoalMilestoneInline]
    readonly_fields = ('milestone_count', 'milestone_completed_count', 'completed_at')


@admin.register(GoalMilestone)
class GoalMilestoneAdmin(admin.ModelAdmin):
    list_display = ('title', 'goal', 'is_completed', 'completed_at')
    list_filter = ('is_completed', )
    search_fields = ('title', 'goal__title')
    list_editable = ('is_completed', )


@admin.register(GoalUpdate)
class GoalUpdateAdmin(admin.ModelAdmin):
    list_display = ('goal', 'user', 'created_at', 'resource')
    list_filter = ('created_at',)
    search_fields = ('content', 'goal__title')
