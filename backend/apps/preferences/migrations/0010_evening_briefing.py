from datetime import time

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("preferences", "0009_insight_attention_policy")]
    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="evening_briefing_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="userpreference",
            name="evening_briefing_time",
            field=models.TimeField(default=time(21, 0)),
        ),
    ]
