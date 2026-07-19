from django.db import migrations


def enable_external_sections(apps, schema_editor):  # type: ignore[no-untyped-def]
    del schema_editor
    BriefingDefinition = apps.get_model("briefings", "BriefingDefinition")
    for definition in BriefingDefinition.objects.filter(name="每日简报"):
        sections = list(definition.enabled_sections)
        if sections != ["calendar", "tasks"]:
            continue
        changed = False
        for key in ("weather", "news"):
            if key not in sections:
                sections.append(key)
                changed = True
        if changed:
            definition.enabled_sections = sections
            definition.save(update_fields=["enabled_sections"])


def disable_external_sections(apps, schema_editor):  # type: ignore[no-untyped-def]
    del schema_editor
    BriefingDefinition = apps.get_model("briefings", "BriefingDefinition")
    for definition in BriefingDefinition.objects.filter(name="每日简报"):
        definition.enabled_sections = [
            key for key in definition.enabled_sections if key not in {"weather", "news"}
        ]
        definition.save(update_fields=["enabled_sections"])


class Migration(migrations.Migration):
    dependencies = [("briefings", "0001_initial")]
    operations = [migrations.RunPython(enable_external_sections, disable_external_sections)]
