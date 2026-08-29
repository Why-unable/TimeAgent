from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("insights", "0001_initial")]
    operations = [
        migrations.AlterField(
            model_name="temporalinsight",
            name="status",
            field=models.CharField(
                choices=[
                    ("open", "Open"),
                    ("snoozed", "Snoozed"),
                    ("dismissed", "Dismissed"),
                    ("actioned", "Actioned"),
                    ("expired", "Expired"),
                    ("false_positive", "False positive"),
                ],
                default="open",
                max_length=16,
            ),
        )
    ]
