from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0001_schedule_plan"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="scheduleplan",
            old_name="planning_sc_user_id_3b1f5d_idx",
            new_name="plan_user_status_created_idx",
        ),
    ]
