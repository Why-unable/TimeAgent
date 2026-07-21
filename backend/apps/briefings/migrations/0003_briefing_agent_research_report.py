from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("briefings", "0002_enable_external_sections")]

    operations = [
        migrations.AddField(
            model_name="briefingrun",
            name="research_report",
            field=models.JSONField(default=dict),
        )
    ]
