from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import GuestAccount


class CurrentUserSerializer(serializers.ModelSerializer[User]):
    display_name = serializers.SerializerMethodField()
    is_email_verified = serializers.SerializerMethodField()
    is_guest = serializers.SerializerMethodField()
    guest_expires_at = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "display_name",
            "is_email_verified",
            "is_staff",
            "is_guest",
            "guest_expires_at",
        ]
        read_only_fields = fields

    @staticmethod
    def get_display_name(user: User) -> str:
        return user.get_full_name() or user.email or user.username

    @staticmethod
    def get_is_email_verified(user: User) -> bool:
        # This project uses Django's built-in ``is_active`` flag as the account
        # activation boundary. Existing active accounts remain valid after the
        # verification feature is introduced.
        return user.is_active and not CurrentUserSerializer.get_is_guest(user)

    @staticmethod
    def get_is_guest(user: User) -> bool:
        return GuestAccount.objects.filter(user=user).exists()

    @staticmethod
    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_guest_expires_at(user: User) -> object | None:
        guest_account = GuestAccount.objects.filter(user=user).only("expires_at").first()
        return guest_account.expires_at if guest_account is not None else None


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
