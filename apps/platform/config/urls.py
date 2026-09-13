from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from workspace import views, connection_views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('health/', views.health, name='health'),
    path('accounts/login/', views.SignInView.as_view(), name='login'),
    path('accounts/logout/', auth.LogoutView.as_view(), name='logout'),
    path('accounts/password/', auth.PasswordChangeView.as_view(template_name='registration/password.html', success_url='/accounts/password/done/'), name='password_change'),
    path('accounts/password/done/', auth.PasswordChangeDoneView.as_view(template_name='registration/password_done.html'), name='password_change_done'),
    path('home/', views.page, name='home'),
    path('devices/', views.page, {'section': 'devices'}, name='devices'),
    path('devices/add/', views.page, {'section': 'onboarding'}, name='onboarding'),
    path('apps/', views.page, {'section': 'apps'}, name='apps'),
    path('connections/', connection_views.connections, name='connections'),
    path('connections/<uuid:pk>/replace/', connection_views.replace_key, name='replace_key'),
    path('connections/<uuid:pk>/delete/', connection_views.delete_connection, name='delete_connection'),
    path('connections/<uuid:pk>/voice/', connection_views.voice_preview, name='voice_preview'),
    path('connections/<uuid:pk>/ticket/', connection_views.audio_ticket, name='audio_ticket'),
    path('settings/', views.settings, name='settings'),
    path('admin/', admin.site.urls),
]
