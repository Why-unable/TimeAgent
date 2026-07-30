from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("preferences", "0005_alter_userpreference_approval_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="daily_briefing_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
