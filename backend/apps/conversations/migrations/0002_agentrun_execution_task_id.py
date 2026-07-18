from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("conversations", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="agentrun",
            name="execution_task_id",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
    ]
