from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        login_identifier = username or kwargs.get(UserModel.USERNAME_FIELD)
        if not login_identifier or password is None:
            return None

        user = UserModel.objects.filter(
            Q(username__iexact=login_identifier) | Q(email__iexact=login_identifier)
        ).first()
        if user is None:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None