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
