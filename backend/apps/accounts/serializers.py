from django.contrib.auth.models import User
from rest_framework import serializers


class CurrentUserSerializer(serializers.ModelSerializer[User]):
    display_name = serializers.SerializerMethodField()
    is_email_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "is_email_verified", "is_staff"]
        read_only_fields = fields

    @staticmethod
    def get_display_name(user: User) -> str:
        return user.get_full_name() or user.email or user.username

    @staticmethod
    def get_is_email_verified(user: User) -> bool:
        # This project uses Django's built-in ``is_active`` flag as the account
        # activation boundary. Existing active accounts remain valid after the
        # verification feature is introduced.
        return user.is_active


class RegisterSerializer(serializers.Serializer[dict[str, str]]):
    email = serializers.EmailField(max_length=254)
    nickname = serializers.CharField(max_length=150, trim_whitespace=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)


class NicknameUpdateSerializer(serializers.Serializer[dict[str, str]]):
    nickname = serializers.CharField(max_length=150, trim_whitespace=True)


class EmailVerificationConfirmSerializer(serializers.Serializer[dict[str, str]]):
    uid = serializers.CharField(max_length=128)
    token = serializers.CharField(max_length=512)


class EmailVerificationRequestSerializer(serializers.Serializer[dict[str, str]]):
    email = serializers.EmailField(max_length=254)


class LoginSerializer(serializers.Serializer[dict[str, str]]):
    identifier = serializers.CharField(max_length=254, trim_whitespace=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)


class PasswordResetRequestSerializer(serializers.Serializer[dict[str, str]]):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer[dict[str, str]]):
    uid = serializers.CharField(max_length=128)
    token = serializers.CharField(max_length=512)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)


class AuthTokenSerializer(serializers.Serializer[dict[str, object]]):
    token = serializers.CharField(read_only=True)
    user = CurrentUserSerializer(read_only=True)
