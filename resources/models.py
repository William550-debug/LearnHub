from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from django.conf import settings
from django.template.defaultfilters import slugify
from core.models import Category
from datetime import timedelta # Used for Course duration
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericRelation

# --- 1. Tag Model (Unchanged) ---
class Tag(models.Model):
    """
    Tags are used to categorize the resources.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    class Meta:
        ordering = ('name',)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

# --- 2. Base Resource Model (Abstract) ---
class BaseResource(models.Model):
    """
    Abstract Base Class defining all common fields for Book, Article, and Course.
    This model does not create a table in the database.
    """
    DIFFICULTY_CHOICES = [
        ('B', 'Beginner'),
        ('I', 'Intermediate'),
        ('A', 'Advanced'),
    ]

    # Core Data
    title = models.CharField(max_length=200)
    # Slug is unique across ALL resource types
    slug = models.SlugField(max_length=200, unique=True, editable=False)
    # URL is optional now, as content might be internal (e.g., Article)
    url = models.URLField(max_length=500, blank=True, null=True)
    description = models.TextField(max_length=1000)
    difficulty = models.CharField(max_length=1, choices=DIFFICULTY_CHOICES)

    # Relationships
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        # FIX: Use %(app_label)s_%(class)s to ensure a unique related_name for each child model
        related_name='%(app_label)s_%(class)s_related',
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        # FIX: Unique related_name for Category -> Resource
        related_name='%(app_label)s_%(class)s_resources',
    )
    tags = models.ManyToManyField(
        Tag,
        related_name='%(app_label)s_%(class)s_tags',
    )

    # Metadata & Approval
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Crucial change: Resources must be approved before public display
    is_approved = models.BooleanField(default=True)
    views = models.PositiveIntegerField(default=0)

    # Computed Statistics (Cached values)
    upvote_count = models.IntegerField(default=0)
    saved_count = models.IntegerField(default=0)


    class Meta:
        # KEY: Makes this an abstract class, preventing DB table creation
        abstract = True
        ordering = ('-created_at',)

    def save(self, *args, **kwargs):
        if not self.slug:
            original_slug = slugify(self.title)
            unique_slug = original_slug
            num = 1
            # Check for slug uniqueness across ALL concrete models
            while (Book.objects.filter(slug=unique_slug).exists() or
                   Article.objects.filter(slug=unique_slug).exists() or
                   Course.objects.filter(slug=unique_slug).exists()):
                unique_slug = f'{original_slug}-{num}'
                num += 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    def get_resource_type(self):
        """Returns the type of the concrete class (e.g., 'Book', 'Article')."""
        return self.__class__.__name__


# --- 3. Concrete Resource Models (Multi-Table Inheritance) ---

class Comment(models.Model):
    """
        User comments on resources (now linked to BaseResource via the concrete models).
        """
    # To link comments to ANY concrete resource type (Book, Article, Course),
    # we use a Generic Foreign Key, but for simplicity, we'll keep the direct
    # ForeignKey to Resource in this context. *Assuming your core model structure
    # already handles this association.*
    # For now, we'll link to BaseResource's slug/id approach which is not ideal,
    # so we'll revert to the original simplified Foreign Key to Resource to maintain compatibility
    # with the existing views, and assume Resource is now one of the concrete types
    # **NOTE: For production, you should use Generic Relations here.**

    # Reverting to original resource FK for compatibility with original views
    # Assuming `resource` field on Comment points to the BaseResource type
    # For now, we'll keep this simplified structure:

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()

    resource = GenericForeignKey('content_type', 'object_id')

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='resource_comments', )
    content = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
    )

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f" Comment by {self.author.email} on {self.resource.title}"

class UserResourceInteraction(models.Model):
    """
        Tracks how a specific user has interacted with a specific resource.

        """
    # 1 Generic fields
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()

    resource = GenericForeignKey('content_type', 'object_id')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='resource_interactions',
    )
    # Links to the BaseResource's ID, which is shared by all concrete models

    # Interaction Flags
    upvoted = models.BooleanField(default=False)
    saved = models.BooleanField(default=False)
    completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'content_type', 'object_id')
        verbose_name = "User Resource Interaction"
        verbose_name_plural = "User Resource Interactions"

    def __str__(self):
        return f"{self.user.email} interaction with {self.resource.title}"



class Book(BaseResource):
    """
    A specific type of resource for downloadable books/documents.
    Inherits all fields from BaseResource.
    """
    # Unique fields for Book
    file = models.FileField(
        upload_to='resources/books/%Y/%m/',
        help_text='Upload the book file (PDF, EPUB, etc.)'
    )
    pages = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Total number of pages in the book'
    )
    comments = GenericRelation(Comment)
    interactions = GenericRelation(UserResourceInteraction)
    class Meta:
        verbose_name = "Book"
        verbose_name_plural = "Books"




class Article(BaseResource):
    """
    A specific type of resource for rich-text, blog-style content.
    Inherits all fields from BaseResource.
    """
    # Unique fields for Article
    # Requires a rich text editor widget in the form (e.g., CKEditor)
    content = models.TextField(
        help_text='The full content of the article (supports rich text/Markdown)'
    )
    banner_image = models.ImageField(
        upload_to='resources/articles/%Y/%m/',
        null=True, blank=True,
        help_text='A banner image for the article'

    )

    interactions = GenericRelation(UserResourceInteraction)
    comments = GenericRelation(Comment)

    class Meta:
        verbose_name = "Article"
        verbose_name_plural = "Articles"


class Course(BaseResource):
    """
    A specific type of resource that acts as a container for a learning roadmap,
    pulling content from other resources and APIs.
    Inherits all fields from BaseResource.
    """
    # Unique fields for Course
    estimated_duration = models.DurationField(
        default=timedelta(days=7),
        help_text='Estimated time to complete the course (e.g., 7 days)'
    )
    # The roadmap itself is generated dynamically in the view.
    comments = GenericRelation(Comment)
    interactions = GenericRelation(UserResourceInteraction)
    class Meta:
        verbose_name = "Course"
        verbose_name_plural = "Courses"


# --- 4. Supporting Models (Interaction & Comment) ---







class CourseProgress(models.Model):
    """
    Tracks a user's progress through a specific Course.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='course_progresses'
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='progress'
    )
    # The step number in the dynamically generated roadmap
    current_step = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    last_accessed = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'course')
        verbose_name = "Course Progress"
        verbose_name_plural = "Course Progresses"
        ordering = ('last_accessed',)