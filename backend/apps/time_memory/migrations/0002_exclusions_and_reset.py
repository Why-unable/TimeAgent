import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("time_memory", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="timememoryrefreshstate",
            name="reset_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="TimeMemoryExclusion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "exclusion_type",
                    models.CharField(
                        choices=[("place", "Place"), ("pattern", "Pattern")], max_length=16
                    ),
                ),
                ("key", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="time_memory_exclusions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="timememoryexclusion",
            constraint=models.UniqueConstraint(
                fields=("user", "exclusion_type", "key"), name="time_memory_unique_exclusion"
            ),
        ),
    ]
