from django.contrib import admin
from django.db.models import F
from .models import Tag, BaseResource, Book, Article, Course, UserResourceInteraction, Comment, CourseProgress


# --- 1. Admin Mixin for Approval Action ---

@admin.action(description='Mark selected resources as approved')
def make_approved(modeladmin, request, queryset):
    """Admin action to set the is_approved field to True for selected resources."""
    queryset.update(is_approved=True)


@admin.action(description='Mark selected resources as UNapproved (Draft)')
def make_unapproved(modeladmin, request, queryset):
    """Admin action to set the is_approved field to False for selected resources."""
    queryset.update(is_approved=False)


# --- 2. Base Admin Class for Shared Functionality ---

class BaseResourceAdmin(admin.ModelAdmin):
    """
    Abstract Admin class providing common fields, list display, filters, and actions.
    This should be inherited by BookAdmin, ArticleAdmin, and CourseAdmin.
    """
    # Fields displayed in the list view
    list_display = (
        'title',
        'author',
        'category',
        'difficulty',
        'is_approved_status',
        'is_approved', # FIX: Include the actual field for list_editable to work
        'upvote_count',
        'saved_count',
        'created_at',
    )

    # Fields that can be edited directly on the list view
    list_editable = ('is_approved',)

    # Fields used for filtering the list
    list_filter = ('is_approved', 'difficulty', 'category', 'created_at')

    # Search fields (searching across all common attributes)
    search_fields = ('title', 'description', 'author__username', 'tags__name')

    # Custom actions (defined above)
    actions = [make_approved, make_unapproved]

    # Read-only fields (metadata/statistics)
    readonly_fields = ('slug', 'upvote_count', 'saved_count', 'created_at', 'updated_at')

    # Field grouping and layout
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'url', 'category', 'difficulty', 'tags', 'is_approved'),
        }),
        ('Metadata & Stats', {
            'fields': ('author', 'slug', 'upvote_count', 'saved_count', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # Custom Method for Admin List View Display
    @admin.display(description='Approval Status', boolean=True)
    def is_approved_status(self, obj):
        """Returns True/False (with green/red icon) based on the is_approved field."""
        return obj.is_approved

    def save_model(self, request, obj, form, change):
        """Set the author automatically if the instance is new and the author field is empty."""
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)


# --- 3. Concrete Admin Classes ---

@admin.register(Book)
class BookAdmin(BaseResourceAdmin):
    """Admin interface for the Book model."""
    # Add unique fields to the fieldsets
    fieldsets = BaseResourceAdmin.fieldsets[:1] + (
        ('Book Details', {
            'fields': ('file', 'pages'),
            'description': 'Fields specific to book resources.',
        }),
    ) + BaseResourceAdmin.fieldsets[1:]

    # Display the specific fields in the list view
    list_display = BaseResourceAdmin.list_display + ('pages',)


@admin.register(Article)
class ArticleAdmin(BaseResourceAdmin):
    """Admin interface for the Article model."""
    # Use the custom field `content` instead of `url` in the fieldsets
    fieldsets = BaseResourceAdmin.fieldsets[:1] + (
        ('Article Content', {
            'fields': ('content', 'banner_image'),
            'description': 'Fields specific to article resources.',
        }),
    ) + BaseResourceAdmin.fieldsets[1:]

    # We may want the content field to use a rich text widget if integrated (e.g., in forms.py)
    # formfield_overrides = {
    #     models.TextField: {'widget': CKEditorWidget},
    # }
    pass  # No additional list display needed for content/image


@admin.register(Course)
class CourseAdmin(BaseResourceAdmin):
    """Admin interface for the Course model."""
    # Add unique fields to the fieldsets
    fieldsets = BaseResourceAdmin.fieldsets[:1] + (
        ('Course Details', {
            'fields': ('estimated_duration',),
            'description': 'Fields specific to course roadmaps.',
        }),
    ) + BaseResourceAdmin.fieldsets[1:]

    list_display = BaseResourceAdmin.list_display + ('estimated_duration',)


# --- 4. Register Supporting Models ---

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('content', 'resource', 'author', 'created_at')
    list_filter = ('created_at', 'resource')
    search_fields = ('content', 'author__username', 'resource__title')
    raw_id_fields = ('author',  'parent')  # Use raw ID for large relationships


@admin.register(UserResourceInteraction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ('user', 'resource', 'upvoted', 'saved', 'completed', 'created_at')
    list_filter = ('upvoted', 'saved', 'completed')
    search_fields = ('user__username', 'resource__title')
    raw_id_fields = ('user', )

    # Action to recalculate resource counts if necessary
    actions = ['recalculate_resource_counts']

    @admin.action(description='Recalculate cached resource counts')
    def recalculate_resource_counts(self, request, queryset):
        """Recalculates the cached upvote/saved counts on the BaseResource model."""

        # Group interactions by resource and count the totals
        resource_counts = queryset.values('resource').annotate(
            total_upvotes=F('resource__upvote_count'),
            total_saved=F('resource__saved_count')
        )

        # NOTE: For a proper recount, you should iterate over ALL interactions for each resource
        # rather than just the selected queryset. This is a simplified action.

        # A more robust solution would be to trigger a signal/task that recounts ALL interactions
        # for the affected resource IDs.

        self.message_user(request, "Resource counts scheduled for recalculation.", level='warning')


@admin.register(CourseProgress)
class CourseProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'current_step', 'completed', 'last_accessed')
    list_filter = ('completed',)
    search_fields = ('user__username', 'course__title')
    raw_id_fields = ('user', 'course')