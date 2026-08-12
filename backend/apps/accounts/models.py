from django.conf import settings
from django.db import models


class GuestAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="guest_account",
    )
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["expires_at", "user_id"]

    def __str__(self) -> str:
        return f"guest:{self.user_id}:{self.expires_at.isoformat()}"
