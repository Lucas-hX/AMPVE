import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('workspace', '0006_firmware_deployments')]

    operations = [
        migrations.CreateModel(
            name='DeviceConsoleSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('last_activity_at', models.DateTimeField(auto_now_add=True)),
                ('device_seen_at', models.DateTimeField(editable=False, null=True)),
                ('ended_at', models.DateTimeField(editable=False, null=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='console_sessions', to='workspace.device')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='device_console_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='DeviceConsoleState',
            fields=[
                ('device', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='console_state', serialize=False, to='workspace.device')),
                ('revision', models.PositiveIntegerField(default=0)),
                ('page', models.CharField(default='home', max_length=16)),
                ('display_mode', models.CharField(default='virtual', max_length=16)),
                ('remote_allowed', models.BooleanField(default=True)),
                ('last_command_id', models.UUIDField(editable=False, null=True)),
                ('last_command_result', models.CharField(blank=True, editable=False, max_length=16)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='DeviceConsoleCommand',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('client_sequence', models.PositiveIntegerField()),
                ('kind', models.CharField(max_length=16)),
                ('input_source', models.CharField(max_length=16)),
                ('target', models.CharField(max_length=32)),
                ('x', models.PositiveSmallIntegerField(null=True)),
                ('y', models.PositiveSmallIntegerField(null=True)),
                ('state', models.CharField(default='pending', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('dispatched_at', models.DateTimeField(editable=False, null=True)),
                ('acknowledged_at', models.DateTimeField(editable=False, null=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='console_commands', to='workspace.device')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='commands', to='workspace.deviceconsolesession')),
            ],
            options={'ordering': ['created_at']},
        ),
        migrations.AddConstraint(
            model_name='deviceconsolecommand',
            constraint=models.UniqueConstraint(fields=('session', 'client_sequence'), name='console_command_sequence_unique'),
        ),
    ]
