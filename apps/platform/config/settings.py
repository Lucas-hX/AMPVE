import json
import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent.parent
TESTING = os.environ.get('AMPVE_TESTING') == '1'
CONFIG_PATH = Path(os.environ.get('AMPVE_CONFIG', '/home/ampve/.config/ampve/platform.json'))
CONFIG = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
FIRMWARE_REVIEW_ROOT = CONFIG.get('firmware_review_root', '/home/ampve/.local/state/ampve/firmware-review-stock-v1')
FIRMWARE_RELEASE_ROOT = CONFIG.get('firmware_release_root', '/home/ampve/.local/state/ampve/firmware-releases')
FIRMWARE_PUBLISHER_TRUST = CONFIG.get('firmware_publisher_trust', '/home/ampve/.config/ampve/firmware-publisher-trust.json')
SECRET_KEY = CONFIG.get('secret_key', '')
if TESTING:
    SECRET_KEY = 'test-only-not-a-deployment-secret-key-000000000000000000'
if not SECRET_KEY:
    raise RuntimeError('Create private AMPVE_CONFIG with a secret_key before starting.')
DEBUG = False
ALLOWED_HOSTS = ['ampve.com', 'www.ampve.com', 'localhost', '127.0.0.1']
CSRF_TRUSTED_ORIGINS = ['https://ampve.com', 'https://www.ampve.com']
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
                  'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
                  'axes', 'workspace']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware',
              'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware',
              'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
              'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware',
              'axes.middleware.AxesMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'],
              'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request',
              'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': CONFIG.get('db_name', 'ampve'),
                        'USER': CONFIG.get('db_user', 'ampve'), 'HOST': CONFIG.get('db_host', '/run/postgresql-neurosis'),
                        'PORT': CONFIG.get('db_port', '5433'), 'CONN_MAX_AGE': 60}}
if TESTING:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
AUTH_USER_MODEL = 'workspace.User'
AUTHENTICATION_BACKENDS = ['axes.backends.AxesStandaloneBackend', 'django.contrib.auth.backends.ModelBackend']
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.' + name} for name in
    ['UserAttributeSimilarityValidator', 'MinimumLengthValidator', 'CommonPasswordValidator', 'NumericPasswordValidator']]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']
AXES_CLIENT_IP_CALLABLE = 'workspace.security.client_ip'
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'registration/locked.html'
# Do not retain request bodies or provider secrets in authentication records.
AXES_SENSITIVE_PARAMETERS = ['username', 'password']
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = REPO_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static', ('brandkit', REPO_DIR / 'images/ampve-brand-kit-v1')]
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
if TESTING:
    STORAGES['staticfiles']['BACKEND'] = 'django.contrib.staticfiles.storage.StaticFilesStorage'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'landing'
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 43200
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = not TESTING
# The origin listens only on loopback and accepts traffic from the local tunnel.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

C6_PROBE_ROOT = CONFIG.get("c6_probe_root", "/home/ampve/.local/state/ampve/c6-probe-unselected")
