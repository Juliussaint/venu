from django.contrib import admin
from .models import (
    Event, Session, 
    Question, QuestionChoice, 
    Participant, Registration, 
    RegistrationAnswer, Resource
)


admin.site.site_header = "Venu Event Management"
admin.site.site_title = "Venu Admin"
admin.site.index_title = "Venu Dashboard"

# --- INLINES ---

class SessionInline(admin.TabularInline):
    model = Session
    extra = 1
    fields = ('title', 'speaker', 'start_time', 'end_time', 'capacity', 'is_active')

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    fields = ('label', 'field_type', 'required', 'order')
    # Note: You add choices inside the Question admin page, not directly here

class QuestionChoiceInline(admin.TabularInline):
    model = QuestionChoice
    extra = 3

# --- ADMINS ---

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_date', 'location', 'is_published')
    list_filter = ('is_published', 'start_date')
    search_fields = ('title', 'location')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [SessionInline, QuestionInline] # Added QuestionInline here

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'event', 'speaker', 'start_time', 'capacity')
    list_filter = ('event',)
    search_fields = ('title', 'speaker')

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('label', 'event', 'field_type', 'required')
    list_filter = ('event',)
    search_fields = ('label',)
    inlines = [QuestionChoiceInline] # Add choices (options) here

@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ('participant', 'event', 'status', 'created_at')
    list_filter = ('status', 'event', 'created_at')
    search_fields = ('participant__name', 'participant__email')

@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone')
    search_fields = ('name', 'email')

# Optional: Useful to see raw answers, but usually not needed if you view Registration
@admin.register(RegistrationAnswer)
class RegistrationAnswerAdmin(admin.ModelAdmin):
    list_display = ('registration', 'question', 'value')
    search_fields = ('registration__participant__name', 'question__label')

@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'event', 'resource_type', 'requires_check_in')
    list_filter = ('event', 'resource_type')