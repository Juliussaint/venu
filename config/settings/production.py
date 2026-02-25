from .local import *

SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]


STATIC_URL = '/static/'
STATIC_ROOT = Path(BASE_DIR) / 'staticfiles'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]


MEDIA_URL = 'https://media.venu.gpibimanuelcimahi.org/'
MEDIA_ROOT = 'home/gpibima1/media.venu.gpibimanuelcimahi'


STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}



CSRF_COOKIE_SECURE = True

SESSION_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 3600

SECURE_SSL_REDIRECT = True

SECURE_HSTS_INCLUDE_SUBDOMAINS = True

SECURE_HSTS_PRELOAD = True

CONN_MAX_AGE = None

USE_X_FORWARDED_HOST = True

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')