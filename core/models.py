import uuid
from django.db import models
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.conf import settings

class Event(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, help_text="Used for the URL, e.g., 'tech-summit-2024'")
    description = models.TextField(blank=True)
    cover_image = models.ImageField(upload_to='event_covers/', blank=True, null=True)
    location = models.CharField(max_length=255, help_text="Venue or 'Online'")
    
    requires_approval = models.BooleanField(
        default=True, 
        help_text="Uncheck this to automatically approve all registrations."
    )

    start_date = models.DateField()
    end_date = models.DateField()
    
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('core:event-detail', kwargs={'slug': self.slug})


class Session(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='sessions')
    
    title = models.CharField(max_length=200)
    speaker = models.CharField(max_length=200, blank=True, help_text="Name of the speaker/host")
    description = models.TextField(blank=True)
    
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    capacity = models.PositiveIntegerField(default=0, help_text="Set 0 for unlimited")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['start_time']

    def __str__(self):
        return f"{self.title} - {self.event.title}"
    

class Participant(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    
    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.email})"


class Question(models.Model):
    FIELD_TYPES = (
        ('text', 'Text'),
        ('select', 'Dropdown'),
        ('radio', 'Radio Buttons'),
        ('checkbox', 'Checkbox'),
    )
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='questions')
    label = models.CharField(max_length=255, help_text="The question text")
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default='text')
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.label} ({self.event.title})"


class QuestionChoice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=255)

    def __str__(self):
        return self.text


class Registration(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='registrations')
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='registrations')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        # Prevent duplicate registration for the same event
        unique_together = ('event', 'participant')

    def __str__(self):
        return f"{self.participant.name} - {self.event.title} ({self.status})"


class RegistrationAnswer(models.Model):
    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    value = models.TextField(blank=True) # Stores the answer

    class Meta:
        unique_together = ('registration', 'question')

    def __str__(self):
        return f"{self.question.label}: {self.value}"
    

class Attendance(models.Model):
    registration = models.ForeignKey('Registration', on_delete=models.CASCADE, related_name='attendances')
    session = models.ForeignKey('Session', on_delete=models.CASCADE, related_name='attendances')
    
    checked_in_at = models.DateTimeField(auto_now_add=True)
    scanned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        # Prevent checking in twice for the same session
        unique_together = ('registration', 'session')

    def __str__(self):
        return f"{self.registration.participant.name} @ {self.session.title}"
    

def resource_upload_path(instance, filename):
    # File will be uploaded to media/resources/<event_slug>/<filename>
    return f'resources/{instance.event.slug}/{filename}'

class Resource(models.Model):
    RESOURCE_TYPES = (
        ('pdf', 'PDF Document'),
        ('image', 'Image'),
        ('video', 'Video Link'),
        ('other', 'Other File'),
    )

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='resources')
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='resources', null=True, blank=True, help_text="Leave blank for general event resources")
    
    title = models.CharField(max_length=200)
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPES, default='pdf')
    
    # For PDFs, Images, etc.
    file = models.FileField(upload_to=resource_upload_path, blank=True, null=True)
    
    # For Video Links (YouTube/Vimeo)
    video_url = models.URLField(blank=True, null=True)

    # Unlock Conditions
    unlock_time = models.DateTimeField(null=True, blank=True, help_text="Leave blank for immediate access")
    requires_check_in = models.BooleanField(default=False, help_text="Require attendance before downloading")

    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'title']

    def __str__(self):
        return f"{self.title} ({self.event.title})"