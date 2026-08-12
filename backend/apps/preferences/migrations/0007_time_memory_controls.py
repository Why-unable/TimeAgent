from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("preferences", "0006_userpreference_daily_briefing_enabled")]

    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="time_memory_allow_context_injection",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="userpreference",
            name="time_memory_allow_generation",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="userpreference",
            name="time_memory_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
