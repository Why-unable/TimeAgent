from django.db import migrations, models


def copy_run_anchor(apps, schema_editor):
    del schema_editor
    agent_run = apps.get_model("conversations", "AgentRun")
    for run in agent_run.objects.only("id", "created_at").iterator():
        agent_run.objects.filter(pk=run.pk).update(anchor_at=run.created_at)


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0004_agentrun_synthetic_input_agentrun_trigger_payload_and_more")
    ]

    operations = [
        migrations.AddField(
            model_name="agentrun",
            name="anchor_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name="agentrun",
            name="anchor_timezone",
            field=models.CharField(default="Asia/Shanghai", max_length=64),
            preserve_default=False,
        ),
        migrations.RunPython(copy_run_anchor, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="agentrun",
            name="anchor_at",
            field=models.DateTimeField(),
        ),
    ]
