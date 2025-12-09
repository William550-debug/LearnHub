from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserProfile


User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    create a Userprofile whenever a new user is created

        :param sender:
    :param instance:
    :param created:
    :param kwargs:
    :return:
    """
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
        Save the userProfile whenever the user is saved
    :param sender:
    :param instance:
    :param kwargs:
    :return:
    """

    try:
        instance.profile.save()
    except UserProfile.DoesNotExist:
        #if user profile does not exist create
        UserProfile.objects.create(user=instance)

