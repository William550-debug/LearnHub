# learnhub/core/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

UserModel = get_user_model()


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)

        try:
            # Try to fetch user by email (case-insensitive)
            user = UserModel.objects.get(Q(email__iexact=username))
        except UserModel.DoesNotExist:
            # Run the default password hasher once to reduce timing difference
            UserModel().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None