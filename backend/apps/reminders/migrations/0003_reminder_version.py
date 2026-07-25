from django.core.validators import MinValueValidator
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("reminders", "0002_task_links_and_scheduling")]

    operations = [
        migrations.AddField(
            model_name="reminder",
            name="version",
            field=models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)]),
        ),
        migrations.AddConstraint(
            model_name="reminder",
            constraint=models.CheckConstraint(
                condition=Q(("version__gte", 1)),
                name="reminder_version_positive",
            ),
        ),
    ]
