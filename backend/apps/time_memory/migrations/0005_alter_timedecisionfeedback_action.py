from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("time_memory", "0004_time_decision_feedback")]
    operations = [
        migrations.AlterField(
            model_name="timedecisionfeedback",
            name="action",
            field=models.CharField(
                choices=[
                    ("accept", "Accept"),
                    ("override", "Override"),
                    ("disable", "Disable"),
                    ("too_short", "Too short"),
                    ("too_long", "Too long"),
                ],
                max_length=16,
            ),
        )
    ]
