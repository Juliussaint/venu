import os
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView
from .models import (
    Event, Session, Participant, Registration, 
    RegistrationAnswer, Attendance, Resource
)
from .forms import RegistrationForm

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse

import qrcode
from io import BytesIO

from django.utils import timezone
from django.contrib import messages

from django.template.loader import render_to_string
from weasyprint import HTML

from django.core.files.storage import default_storage
from wsgiref.util import FileWrapper


class EventListView(ListView):
    model = Event
    template_name = 'core/event_list.html'
    context_object_name = 'events'
    
    def get_queryset(self):
        # Only show published events to the public
        return Event.objects.filter(is_published=True)

class EventDetailView(DetailView):
    model = Event
    template_name = 'core/event_detail.html'
    context_object_name = 'event'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass the sessions related to this event
        context['sessions'] = self.object.sessions.all() 
        return context
    

def event_register(request, slug):
    event = get_object_or_404(Event, slug=slug, is_published=True)
    
    if request.method == 'POST':
        form = RegistrationForm(request.POST, event=event)
        if form.is_valid():
            # 1. Save Participant
            participant, created = Participant.objects.get_or_create(
                email=form.cleaned_data['participant_email'],
                defaults={
                    'name': form.cleaned_data['participant_name'],
                    'phone': form.cleaned_data['participant_phone']
                }
            )
            
            # 2. Check for duplicate registration
            if Registration.objects.filter(event=event, participant=participant).exists():
                # Error handling for duplicate (simple version)
                return render(request, 'core/registration_error.html', {'message': 'You have already registered for this event.'})

            # --- NEW LOGIC START ---
            # Determine status based on Event setting
            if event.requires_approval:
                initial_status = 'pending'
            else:
                initial_status = 'approved'
            # --- NEW LOGIC END ---
            
            # 3. Save Registration
            registration = Registration.objects.create(
                event=event,
                participant=participant,
                status=initial_status
            )

            # 4. Save Dynamic Answers
            for field_name, value in form.cleaned_data.items():
                if field_name.startswith('question_'):
                    question_id = int(field_name.replace('question_', ''))
                    question = event.questions.get(id=question_id)
                    
                    # Handle lists (checkboxes)
                    if isinstance(value, list):
                        value = ", ".join(value)
                        
                    RegistrationAnswer.objects.create(
                        registration=registration,
                        question=question,
                        value=value
                    )
            
            return render(request, 'core/registration_success.html', {'registration': registration})
    else:
        form = RegistrationForm(event=event)

    return render(request, 'core/registration_form.html', {'event': event, 'form': form})


def registration_detail(request, uuid):
    """
    Public view for a participant to see their ticket status.
    Uses the UUID so no login is required.
    """
    registration = get_object_or_404(Registration, uuid=uuid)
    return render(request, 'core/registration_detail.html', {'registration': registration})


# --- MIXIN FOR STAFF ONLY ACCESS ---
class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff
    

class EventDashboardView(StaffRequiredMixin, DetailView):
    model = Event
    template_name = 'core/dashboard/event_dashboard.html'
    context_object_name = 'event'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        registrations = self.object.registrations.all().select_related('participant')
        
        # Stats for cards
        context['total_count'] = registrations.count()
        context['approved_count'] = registrations.filter(status='approved').count()
        context['pending_count'] = registrations.filter(status='pending').count()
        
        # Filter logic
        status_filter = self.request.GET.get('status', 'all')
        if status_filter != 'all':
            registrations = registrations.filter(status=status_filter)
            
        context['registrations'] = registrations
        context['status_filter'] = status_filter
        return context

# HTMX Action Views
@login_required
def approve_registration(request, pk):
    if not request.user.is_staff:
        return HttpResponse("Unauthorized", status=403)
        
    registration = get_object_or_404(Registration, pk=pk)
    registration.status = 'approved'
    registration.save()
    
    # Return the updated row partial
    return render(request, 'core/dashboard/partials/registration_row.html', {'reg': registration})

@login_required
def reject_registration(request, pk):
    if not request.user.is_staff:
        return HttpResponse("Unauthorized", status=403)
        
    registration = get_object_or_404(Registration, pk=pk)
    registration.status = 'rejected'
    registration.save()
    
    # Return the updated row partial
    return render(request, 'core/dashboard/partials/registration_row.html', {'reg': registration})


def registration_qr_code(request, uuid):
    """
    Generates a QR code image for the registration UUID.
    """
    registration = get_object_or_404(Registration, uuid=uuid)
    
    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    # The data inside the QR code is the URL to the check-in scan endpoint
    # We will create the scan endpoint next
    scan_url = request.build_absolute_uri(f"/scan/{registration.uuid}/")
    qr.add_data(scan_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Return image as HTTP response
    buffer = BytesIO()
    img.save(buffer, 'PNG')
    return HttpResponse(buffer.getvalue(), content_type='image/png')


def staff_check_in(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    context = {
        'event': event,
        'active_session': None
    }
    
    # Logic: Auto-detect active session based on current time
    now = timezone.now()
    active_session = event.sessions.filter(start_time__lte=now, end_time__gte=now).first()
    context['active_session'] = active_session
    
    return render(request, 'core/dashboard/check_in.html', context)

# Process Scan (HTMX Endpoint)
def process_check_in(request, uuid):
    if not request.user.is_staff:
        return HttpResponse("Unauthorized", status=403)

    registration = get_object_or_404(Registration, uuid=uuid)
    
    # 1. Validation: Is it approved?
    if registration.status != 'approved':
        return render(request, 'core/dashboard/partials/check_in_result.html', {
            'success': False,
            'message': f"Registration Status: {registration.status.upper()}. Not allowed to enter.",
            'registration': registration
        })

    # 2. Validation: Active Session?
    now = timezone.now()
    active_session = registration.event.sessions.filter(start_time__lte=now, end_time__gte=now).first()
    
    if not active_session:
        return render(request, 'core/dashboard/partials/check_in_result.html', {
            'success': False,
            'message': "No active session right now.",
            'registration': registration
        })

    # 3. Validation: Duplicate?
    if Attendance.objects.filter(registration=registration, session=active_session).exists():
        return render(request, 'core/dashboard/partials/check_in_result.html', {
            'success': False,
            'message': f"Already checked in for {active_session.title}!",
            'registration': registration
        })

    # 4. Success: Create Attendance
    Attendance.objects.create(
        registration=registration,
        session=active_session,
        scanned_by=request.user
    )

    return render(request, 'core/dashboard/partials/check_in_result.html', {
        'success': True,
        'message': f"Welcome! Checked in for {active_session.title}",
        'registration': registration
    })


def download_ticket_pdf(request, uuid):
    """
    Generates a PDF ticket for the participant to download.
    """
    registration = get_object_or_404(Registration, uuid=uuid)

    # 1. Render the HTML template to a string
    # Note: We will create a simplified template 'ticket_pdf.html' for the PDF layout
    html_string = render_to_string('core/ticket_pdf.html', {
        'registration': registration,
        'request': request # Pass request for absolute URLs (images/css)
    })

    # 2. Create PDF object
    # base_url is crucial for loading static files (CSS/Images) in the PDF
    html = HTML(string=html_string, base_url=request.build_absolute_uri())

    # 3. Generate PDF
    pdf_file = html.write_pdf()

    # 4. Return as downloadable attachment
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="VENU_Ticket_{registration.event.title}.pdf"'
    
    return response

def participant_portal(request, uuid):
    """
    The main hub for a participant to view agenda and download resources.
    """
    registration = get_object_or_404(Registration, uuid=uuid)
    event = registration.event
    sessions = event.sessions.all()
    
    # Get all resources for this event
    resources = event.resources.all().order_by('order')
    
    # Logic: Check what user is allowed to access
    now = timezone.now()
    
    # List of resource IDs that are locked
    locked_resources = []
    
    for res in resources:
        is_locked = False
        
        # 1. Check Time Condition
        if res.unlock_time and now < res.unlock_time:
            is_locked = True
            
        # 2. Check Check-In Condition
        if res.requires_check_in:
            # Has the user attended ANY session of this event?
            # Or specifically the session linked to the resource?
            # Let's check if they have ANY attendance for this event.
            attended = Attendance.objects.filter(registration=registration).exists()
            if not attended:
                is_locked = True
        
        if is_locked:
            locked_resources.append(res.id)

    context = {
        'registration': registration,
        'event': event,
        'sessions': sessions,
        'resources': resources,
        'locked_resources': locked_resources,
        'now': now,
    }
    return render(request, 'core/portal/participant_portal.html', context)

def secure_download(request, uuid, resource_id):
    """
    Serves the file only if permission checks pass.
    """
    registration = get_object_or_404(Registration, uuid=uuid)
    resource = get_object_or_404(Resource, pk=resource_id)
    
    # 1. Security Check: Does this resource belong to the registration's event?
    if resource.event != registration.event:
        return HttpResponse("Forbidden", status=403)

    # 2. Security Check: Is registration approved?
    if registration.status != 'approved':
        return HttpResponse("Registration not approved", status=403)

    # 3. Security Check: Time Constraint
    now = timezone.now()
    if resource.unlock_time and now < resource.unlock_time:
        return HttpResponse("Not available yet", status=403)

    # 4. Security Check: Attendance Constraint
    if resource.requires_check_in:
        attended = Attendance.objects.filter(registration=registration).exists()
        if not attended:
            return HttpResponse("You must check-in first", status=403)

    # 5. Serve File
    if not resource.file:
        return HttpResponse("File not found", status=404)

    # Serve the file using Django (good enough for medium traffic)
    # For high traffic, use Nginx X-Accel-Redirect
    file_path = resource.file.path
    file_name = resource.title + os.path.splitext(file_path)[1]
    
    # Use FileWrapper to stream large files efficiently
    wrapper = FileWrapper(open(file_path, 'rb'))
    content_type = 'application/octet-stream' # Force download
    
    response = HttpResponse(wrapper, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{file_name}"'
    response['Content-Length'] = os.path.getsize(file_path)
    return response


def find_ticket(request):
    """
    Allows a user to enter their email to find their registration.
    """
    if request.method == 'POST':
        email = request.POST.get('email')
        
        # Find the participant
        participant = Participant.objects.filter(email__iexact=email).first()
        
        if participant:
            # Get the most recent active registration for this participant
            registration = Registration.objects.filter(participant=participant).order_by('-created_at').first()
            
            if registration:
                # Redirect to their ticket page
                return redirect('core:registration-detail', uuid=registration.uuid)
        
        # If not found
        messages.error(request, "No registration found with that email address.")
    
    return render(request, 'core/find_ticket.html')

