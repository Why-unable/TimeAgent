from django.core.management.base import BaseCommand

from apps.integrations.calendar.oauth_services import CalendarCredentialService


class Command(BaseCommand):
    help = "Re-encrypt calendar OAuth credentials with the primary configured Fernet key."

    def handle(self, *args: object, **options: object) -> None:
        del args, options
        count = CalendarCredentialService.rotate_encryption()
        self.stdout.write(self.style.SUCCESS(f"Rotated {count} calendar OAuth credential(s)."))
