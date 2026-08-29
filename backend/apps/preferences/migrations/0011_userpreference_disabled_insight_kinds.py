from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("preferences", "0010_evening_briefing")]
    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="disabled_insight_kinds",
            field=models.JSONField(blank=True, default=list),
        )
    ]
