from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        user = self.model(email=email.strip().lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if not extra_fields['is_staff'] or not extra_fields['is_superuser']:
            raise ValueError('A superuser must have both administrator flags')
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        constraints = [models.UniqueConstraint(Lower('email'), name='user_email_case_insensitive')]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class Application(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    target_hardware = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=[('preview', 'In development')], default='preview')

    def __str__(self):
        return self.name


class ProviderConnection(models.Model):
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='provider_connections')
    provider = models.CharField(max_length=16, choices=[('gemini', 'Gemini Live'), ('openai', 'OpenAI Realtime')])
    label = models.CharField(max_length=80)
    encrypted_key = models.TextField(editable=False)
    revision = models.PositiveIntegerField(default=1, editable=False)
    validation = models.CharField(max_length=16, default='untested', editable=False)
    checked_at = models.DateTimeField(null=True, editable=False)
    result_code = models.CharField(max_length=40, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.label


class AudioGrant(models.Model):
    token_hash = models.CharField(max_length=64, unique=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    connection = models.ForeignKey(ProviderConnection, on_delete=models.CASCADE)
    revision = models.PositiveIntegerField()
    browser_session = models.CharField(max_length=40)
    mode = models.CharField(max_length=8, choices=[('check', 'check'), ('voice', 'voice')])
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)


class AudioSession(models.Model):
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    connection = models.ForeignKey(ProviderConnection, null=True, on_delete=models.SET_NULL)
    revision = models.PositiveIntegerField()
    provider = models.CharField(max_length=16)
    mode = models.CharField(max_length=8)
    status = models.CharField(max_length=16, default='starting')
    result_code = models.CharField(max_length=40, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True)


class Device(models.Model):
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices')
    name = models.CharField(max_length=80)
    hardware_profile = models.CharField(max_length=80)
    credential_hash = models.CharField(max_length=64, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, editable=False)
    last_seen = models.DateTimeField(null=True, editable=False)
    firmware_version = models.CharField(max_length=80, blank=True)
    chip_revision = models.CharField(max_length=20, blank=True)
    transport = models.CharField(max_length=16, blank=True)
    hardware_report = models.JSONField(default=dict, editable=False)
    hardware_reported_at = models.DateTimeField(null=True, editable=False)
    config_version = models.PositiveIntegerField(default=1)
    acknowledged_version = models.PositiveIntegerField(default=0)
    volume = models.PositiveSmallIntegerField(default=40)
    microphone_muted = models.BooleanField(default=True)

    @property
    def connection_state(self):
        from django.utils import timezone
        from datetime import timedelta
        if self.revoked_at:
            return 'Revoked'
        if not self.last_seen:
            return 'Awaiting device'
        return 'Online' if self.last_seen > timezone.now() - timedelta(seconds=90) else 'Offline'

    class Meta:
        ordering = ['-created_at']


class DeviceEnrollment(models.Model):
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code_hash = models.CharField(max_length=64, unique=True)
    proof_hash = models.CharField(max_length=64)
    hardware_profile = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    device = models.OneToOneField(Device, null=True, on_delete=models.CASCADE)


class DeviceRateBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    started_at = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)


class DeviceConsoleSession(models.Model):
    """Short-lived owner authorization for one visual device console."""
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='console_sessions')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_console_sessions')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_activity_at = models.DateTimeField(auto_now_add=True)
    device_seen_at = models.DateTimeField(null=True, editable=False)
    ended_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        ordering = ['-created_at']


class DeviceConsoleState(models.Model):
    """Bounded semantic screen state; it never stores pixels or media."""
    device = models.OneToOneField(Device, primary_key=True, on_delete=models.CASCADE, related_name='console_state')
    revision = models.PositiveIntegerField(default=0)
    page = models.CharField(max_length=16, default='home')
    display_mode = models.CharField(max_length=16, default='virtual')
    remote_allowed = models.BooleanField(default=True)
    last_command_id = models.UUIDField(null=True, editable=False)
    last_command_result = models.CharField(max_length=16, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)


class DeviceConsoleCommand(models.Model):
    """A bounded input event dispatched at most once to avoid reconnect replay."""
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(DeviceConsoleSession, on_delete=models.CASCADE, related_name='commands')
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='console_commands')
    client_sequence = models.PositiveIntegerField()
    kind = models.CharField(max_length=16)
    input_source = models.CharField(max_length=16)
    target = models.CharField(max_length=32)
    x = models.PositiveSmallIntegerField(null=True)
    y = models.PositiveSmallIntegerField(null=True)
    state = models.CharField(max_length=16, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    dispatched_at = models.DateTimeField(null=True, editable=False)
    acknowledged_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['session', 'client_sequence'], name='console_command_sequence_unique')]
        ordering = ['created_at']


class FirmwareRelease(models.Model):
    """Immutable imported signed policy; signing keys never enter the database."""
    id = models.CharField(primary_key=True, max_length=64)
    scope = models.CharField(max_length=64)
    channel = models.CharField(max_length=32)
    sequence = models.PositiveIntegerField()
    policy = models.JSONField()
    directory = models.CharField(max_length=512)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['scope','channel','sequence'], name='firmware_release_sequence_unique')]


class DeviceFirmware(models.Model):
    device = models.OneToOneField(Device, primary_key=True, on_delete=models.CASCADE, related_name='firmware_state')
    release = models.ForeignKey(FirmwareRelease, on_delete=models.PROTECT)
    app_sha256 = models.CharField(max_length=64)
    confirmed_sequence = models.PositiveIntegerField()
    confirmed_at = models.DateTimeField()


class FirmwareDeployment(models.Model):
    import uuid
    ACTIVE = ['queued','downloading','verifying','rebooting']
    STATES = [(value,value.replace('_',' ').capitalize()) for value in ACTIVE + ['confirmed','failed','rolled_back','cancelled']]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='firmware_deployments')
    release = models.ForeignKey(FirmwareRelease, on_delete=models.PROTECT)
    previous_release = models.ForeignKey(FirmwareRelease, on_delete=models.PROTECT, related_name='+')
    previous_app_sha256 = models.CharField(max_length=64)
    idempotency_key = models.UUIDField()
    state = models.CharField(max_length=16, choices=STATES, default='queued')
    report_sequence = models.PositiveIntegerField(default=0)
    bytes_written = models.PositiveIntegerField(default=0)
    last_report = models.JSONField(default=dict)
    error_code = models.CharField(max_length=32, blank=True)
    needs_attention = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['device','idempotency_key'], name='firmware_request_idempotent'),
            models.UniqueConstraint(fields=['device'], condition=models.Q(state__in=['queued','downloading','verifying','rebooting']), name='one_active_firmware_deployment'),
        ]
        ordering = ['-created_at']


class FirmwareDeploymentEvent(models.Model):
    deployment = models.ForeignKey(FirmwareDeployment, on_delete=models.CASCADE, related_name='events')
    sequence = models.PositiveIntegerField()
    report = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['deployment','sequence'], name='firmware_event_sequence_unique')]
