from django.db import models
from django.conf import settings
from django.template.defaultfilters import slugify
from core.models import Category


# Create your models here
#Tag  Model for (content classification)
class Tag(models.Model):
    """
    Tags are used to categorize the resources (eg. tutorial , video m API)
    Distinct from core.Skill which is user focused
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

#2 Resource model (Core content model)
class Resource(models.Model):
    """
    The main model for shared learning resources
    """

    DIFFICULTY_CHOICES = [
        ('B', 'Beginner'),
        ('I', 'Intermediate'),
        ('A', 'Advanced'),
    ]


    #Core Data
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    url = models.URLField(max_length=500)
    description = models.TextField(max_length=1000)
    difficulty = models.CharField(max_length=1, choices=DIFFICULTY_CHOICES)
    views = models.PositiveIntegerField(default=0)

    #defining the relationships
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='shared_resources',
    )

    category= models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name='resources',
    )

    tags = models.ManyToManyField(
        Tag,
        related_name='resources',
    )

    #metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_approved = models.BooleanField(default=True) #to ensure admin has overall moderation


    #computed Statistics (Cached values from the interaction Model)
    upvote_count = models.IntegerField(default=0)
    saved_count = models.IntegerField(default=0)

    class Meta:
        ordering = ('-created_at',)

    def save(self, *args, **kwargs):
        if not self.slug:
            #create a unique slug from the title
            original_slug = slugify(self.title)
            unique_slug = original_slug
            num = 1
            while Resource.objects.filter(slug=unique_slug).exists():
                unique_slug = f'{unique_slug}-{num}'
                num += 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

#3 Comment Model
class Comment(models.Model):
    """
    USer Comments on the resources
    """

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='resource_comments',)
    content = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    #Simple reply structure (Optional but can come in handy)
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

#4 User-Resource Interaction Model( Separating state/actions)
class UserResourceInteraction (models.Model):
    """
    Tracks how a specific user has interacted with a specific resource
    This replaces individual boolean fields on the User Model
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='resource_interactions',
    )

    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name='interactions',
    )


    #Interaction Flags
    upvoted = models.BooleanField(default=False)
    saved = models.BooleanField(default=False)
    completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        #Ensures a user can only interact with a resource once (unique constraints)
        unique_together = ('user', 'resource')
        verbose_name = "User Resource Interaction"
        verbose_name_plural = "User Resource Interactions"

    def __str__(self):
        return f"{self.user.email} interaction with {self.resource.title}"
