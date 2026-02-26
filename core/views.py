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

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT

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
    registration = get_object_or_404(Registration, uuid=uuid)

    # 1. Create a file-like buffer to receive PDF data.
    buffer = BytesIO()

    # 2. Create the PDF object, using the buffer as its "file."
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    # Container for the 'Flowable' objects (elements)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    
    INDIGO = colors.HexColor('#4F46E5') # Tailwind Indigo-600
    GREY = colors.grey
    LIGHT_GREY = colors.lightgrey if hasattr(colors, 'lightgrey') else colors.HexColor('#D3D3D3')

    # Custom Styles
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=INDIGO,
        alignment=TA_CENTER,
        spaceAfter=10
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=GREY,
        alignment=TA_CENTER,
        spaceAfter=20
    )

    header_style = ParagraphStyle(
        'Header',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        alignment=TA_LEFT
    )

    # --- CONTENT GENERATION ---

    # Event Title
    elements.append(Paragraph(registration.event.title, title_style))
    
    # Event Details
    event_info = f"{registration.event.location} | {registration.event.start_date}"
    elements.append(Paragraph(event_info, subtitle_style))
    
    elements.append(Spacer(1, 20))

    # Status Badge Logic
    if registration.status == 'approved':
        status_text = "CONFIRMED"
        status_color = colors.green
    else:
        status_text = "PENDING APPROVAL"
        status_color = colors.orange

    # Create a small table for the status
    status_data = [[status_text]]
    status_table = Table(status_data, colWidths=[8*cm])
    status_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), status_color),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [5, 5, 5, 5]), # Not supported in all ReportLab versions, acts as border
    ]))
    elements.append(status_table)
    
    elements.append(Spacer(1, 30))

    # Participant Info Table
    data = [
        ['Name:', registration.participant.name],
        ['Email:', registration.participant.email],
        ['Reference:', str(registration.uuid)],
    ]

    info_table = Table(data, colWidths=[4*cm, 12*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'), # Align labels right
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),  # Align values left
    ]))
    elements.append(info_table)

    elements.append(Spacer(1, 40))

    # QR CODE GENERATION
    if registration.status == 'approved':
        # Generate QR Code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        scan_url = request.build_absolute_uri(f"/scan/{registration.uuid}/")
        qr.add_data(scan_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        # Save QR image to buffer
        img_buffer = BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Add Image to PDF
        # We use ReportLab's Image class
        qr_image = Image(img_buffer, width=6*cm, height=6*cm)
        qr_image.hAlign = 'CENTER'
        elements.append(qr_image)
        
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("Scan this at the entrance", subtitle_style))
    else:
        elements.append(Paragraph("QR Code will appear once approved", subtitle_style))

    # Footer
    elements.append(Spacer(1, 50))
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=LIGHT_GREY, alignment=TA_CENTER)
    elements.append(Paragraph("Powered by VENU Platform", footer_style))

    # 3. Build the PDF
    doc.build(elements)

    # 4. Get the value of the BytesIO buffer and write it to the response.
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="VENU_Ticket_{registration.event.title}.pdf"'
    response.write(pdf)
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

