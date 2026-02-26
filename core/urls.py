# core/urls.py
from django.urls import path
from .views import (
    EventListView, EventDetailView, event_register, registration_detail,
    EventDashboardView, approve_registration, reject_registration, 
    registration_qr_code, staff_check_in, process_check_in, 
    download_ticket_pdf, participant_portal,secure_download, find_ticket,
    AttendanceListView, StaffHomeView, export_attendance_csv, self_check_in,
)

app_name = 'core'

urlpatterns = [
    path('', EventListView.as_view(), name='event-list'),
    path('event/<slug:slug>/', EventDetailView.as_view(), name='event-detail'),
    path('event/<slug:slug>/register/', event_register, name='event-register'),
    path('ticket/<uuid:uuid>/', registration_detail, name='registration-detail'),
    path('ticket/<uuid:uuid>/qr/', registration_qr_code, name='registration-qr'),
    path('ticket/<uuid:uuid>/download/', download_ticket_pdf, name='download-ticket'),

    # Phase 3: Dashboard
    path('dashboard/', StaffHomeView.as_view(), name='staff-home'),
    path('dashboard/event/<int:pk>/', EventDashboardView.as_view(), name='event-dashboard'),
    path('dashboard/event/<int:pk>/attendance/', AttendanceListView.as_view(), name='attendance-list'),
    path('dashboard/event/<int:event_id>/checkin/', staff_check_in, name='staff-checkin'),
    path('dashboard/event/<int:pk>/export/', export_attendance_csv, name='export-csv'),

    # Phase 3: HTMX Actions
    path('registration/<int:pk>/approve/', approve_registration, name='approve-registration'),
    path('registration/<int:pk>/reject/', reject_registration, name='reject-registration'),

    # Phase 4: Check-in
    path('dashboard/event/<int:event_id>/checkin/', staff_check_in, name='staff-checkin'),
    path('scan/<uuid:uuid>/', process_check_in, name='process-checkin'),

    # Phase 5: Portal
    path('portal/<uuid:uuid>/', participant_portal, name='participant-portal'),
    path('portal/<uuid:uuid>/download/<int:resource_id>/', secure_download, name='secure-download'),
    path('portal/<uuid:uuid>/checkin/<int:session_id>/', self_check_in, name='self-checkin'),

    path('find-ticket/', find_ticket, name='find-ticket'),
]