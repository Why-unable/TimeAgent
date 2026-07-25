from django.core.validators import MinValueValidator
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("tasks", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="task",
            name="version",
            field=models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)]),
        ),
        migrations.AddConstraint(
            model_name="task",
            constraint=models.CheckConstraint(
                condition=Q(("version__gte", 1)),
                name="task_version_positive",
            ),
        ),
    ]
