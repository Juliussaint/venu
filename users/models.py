from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    pass
    # You can add extra fields here later if needed (e.g., phone number)