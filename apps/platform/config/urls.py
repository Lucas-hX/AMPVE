from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from workspace import views, connection_views, device_views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('health/', views.health, name='health'),
    path('accounts/login/', views.SignInView.as_view(), name='login'),
    path('accounts/logout/', auth.LogoutView.as_view(), name='logout'),
    path('accounts/password/', auth.PasswordChangeView.as_view(template_name='registration/password.html', success_url='/accounts/password/done/'), name='password_change'),
    path('accounts/password/done/', auth.PasswordChangeDoneView.as_view(template_name='registration/password_done.html'), name='password_change_done'),
    path('home/', views.page, name='home'),
    path('devices/', device_views.devices, name='devices'),
    path('devices/add/', device_views.onboarding, name='onboarding'),
    path('devices/interface-preview/', device_views.interface_preview, name='interface_preview'),
    path('devices/<uuid:pk>/', device_views.detail, name='device_detail'),
    path('devices/<uuid:pk>/revoke/', device_views.revoke, name='device_revoke'),
    path('api/devices/v1/enroll/', device_views.enrollment_start),
    path('api/devices/v1/enroll/<uuid:pk>/exchange/', device_views.enrollment_exchange),
    path('api/devices/v1/<uuid:pk>/heartbeat/', device_views.heartbeat),
    path('apps/', views.page, {'section': 'apps'}, name='apps'),
    path('connections/', connection_views.connections, name='connections'),
    path('connections/<uuid:pk>/replace/', connection_views.replace_key, name='replace_key'),
    path('connections/<uuid:pk>/delete/', connection_views.delete_connection, name='delete_connection'),
    path('connections/<uuid:pk>/voice/', connection_views.voice_preview, name='voice_preview'),
    path('connections/<uuid:pk>/ticket/', connection_views.audio_ticket, name='audio_ticket'),
    path('settings/', views.settings, name='settings'),
    path('admin/', admin.site.urls),
]
