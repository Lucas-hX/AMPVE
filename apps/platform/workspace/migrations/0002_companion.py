from django.db import migrations


def seed_catalog(apps, schema_editor):
    apps.get_model('workspace', 'Application').objects.get_or_create(slug='companion', defaults={
        'name': 'AMPVE Companion',
        'description': 'Helpful answers, a friendly face, and a little company. A small screen for big possibilities.',
        'target_hardware': 'Waveshare ESP32-P4-WIFI6-Touch-LCD-7B', 'status': 'preview'})


class Migration(migrations.Migration):
    dependencies = [('workspace', '0001_initial')]
    operations = [migrations.RunPython(seed_catalog, migrations.RunPython.noop)]
