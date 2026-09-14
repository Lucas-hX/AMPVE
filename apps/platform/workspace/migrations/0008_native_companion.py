import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('workspace', '0007_device_visual_console')]
    operations = [
        migrations.AddField(
            model_name='audiogrant', name='device',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='audio_grants', to='workspace.device'),
        ),
        migrations.AlterField(
            model_name='audiogrant', name='browser_session',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AlterField(
            model_name='audiogrant', name='mode',
            field=models.CharField(choices=[('check', 'check'), ('voice', 'voice'), ('device', 'device')], max_length=8),
        ),
        migrations.AddField(
            model_name='audiosession', name='device',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='audio_sessions', to='workspace.device'),
        ),
        migrations.CreateModel(
            name='CompanionInstallation',
            fields=[
                ('device', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                    primary_key=True, related_name='companion', serialize=False, to='workspace.device')),
                ('enabled', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('connection', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='companion_installations', to='workspace.providerconnection')),
            ],
        ),
    ]
