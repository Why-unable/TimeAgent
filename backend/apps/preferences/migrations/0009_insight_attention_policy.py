from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("preferences", "0008_weather_location_data_v2")]
    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="proactive_insights_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="userpreference",
            name="insight_daily_notification_limit",
            field=models.PositiveSmallIntegerField(default=3),
        ),
        migrations.AddField(
            model_name="userpreference",
            name="insight_cooldown_minutes",
            field=models.PositiveSmallIntegerField(default=240),
        ),
    ]
