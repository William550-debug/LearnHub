from django.db import models
from django.contrib.auth.models import AbstractUser, PermissionsMixin
from django.contrib.auth.models import BaseUserManager
from django.utils import timezone
from django.template.defaultfilters import slugify #used for auto-generating clean URLs


# Create your models here.
#Phase 1
#custom manager for Email-based authentication
class CustomUserManager(BaseUserManager):
    """
    Custom user manager where them email is the unique identifier
    for authentication instead of username.
    """

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address')

        email = self.normalize_email(email) # Makes "John@GMAIL.com" → "john@gmail.com"

        #autogenerate username from email
        if 'username' not in extra_fields:
            extra_fields['username'] = email.split('@')[0]


        user = self.model(email=email, **extra_fields)  # Creates user object
        user.set_password(password) # Securely hashes the password
        user.save(using=self._db)  # Saves to database
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        creates and saves a superuser with a given email and password. admin users
        :param email:
        :param password:
        :param extra_fields:
        :return:
        """

        extra_fields.setdefault('is_staff', True) # Can access admin site
        extra_fields.setdefault('is_superuser', True) # Has all permissions
        extra_fields.setdefault('is_active', True)  # Account is active

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)

#2 Custom User model
class CustomUser(AbstractUser, PermissionsMixin):

    """
    The main user model for authentication and authorization.
    Uses email for  the unique identification
    """
    username = models.CharField(
        max_length=150,
        unique=True,
        blank=True,
        null=True,
        help_text='Optional. Not used for login.'
    )

    email = models.EmailField(max_length=255, unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    #use the custom Manager
    objects = CustomUserManager()

    #Define the unique identifier for login
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name'] # NO OTHER FIELDS ARE REQUIRED FOR INITIAL CREATION

    #initial typo we are replacing django default user model with a custom one
    """
    fix:!!
        add a unique related name arguments to avoid clashes
        (these fields are inherited from PermissionsMixin)
    
    """
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions ',
        related_name='custom_user_groups',
        related_query_name='custom_user'

    )

    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='custom_user_permissions_set',
        related_query_name='custom user'
    )



    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):

        return self.first_name or  self.email

    def save(self, *args, **kwargs):
        #Auto-generate username from email if not provided
        if not self.username and self.email:
            #use email prefix as username
            self.username = self.email.split('@')[0]

        super().save(*args,**kwargs )



    def __str__(self):
        return self.email

#3 User profile Model (for extended user data)

class Skill(models.Model):
    """
       Represents a specific skill a user possess or a resource covers
       ie(react , Data Science , python )
       Users will link to this model
       """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    description = models.TextField(max_length=200, blank=True)

    # Optional: A counter for how many users/resources use this skill (for ordering/popularity)
    # user_count = models.IntegerField(default=0)

    class Meta:
        ordering = ('name',)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """
    Holds extra , non-authentication related data

    """

    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)

    # feature to add ie skills. computed stats
    skills = models.ManyToManyField( Skill ,blank=True, related_name='users')


    #computes stats
    resource_completed = models.IntegerField(default=0)
    goals_archived_count = models.IntegerField(default=0)
    join_date = models.DateTimeField(default=timezone.now)


    def __str__(self):
        return f"Profile for {self.user.email}"



#Phase 2 implementation


class Category(models.Model):
    """
    Represents broad categories of a user
    ie (Programming , Design , Software engineering , Soft Skills
    Resources will link to this model
    """


    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True, max_length=50)
    icon_class = models.CharField(max_length=50, blank=True,
                                  help_text="Font Awesome class, e.g., fas fa-code")
    class Meta:
        verbose_name_plural = 'categories'
        ordering = ('name',)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class SiteStats(models.Model):
    """
    Optional model for storing site-wide counters (ie landing page)
    There should only ever be one instance of this model
    """

    total_resources = models.IntegerField(default=0)
    total_users = models.IntegerField(default=0)
    total_goals_completed = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Site Statistics'
        verbose_name = 'Site Statistic'

    def  __str__(self):
        return "Site Statistics Instance"

    #Optional : to ensuer only one instance can exist
    def save(self, *args, **kwargs):
        if self.pk is None and SiteStats.objects.exists():
            #prevent creation if one exists
            return
        super().save(*args, **kwargs)









