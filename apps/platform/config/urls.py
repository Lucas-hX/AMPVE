from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from workspace import views

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
    path('connections/', views.page, {'section': 'connections'}, name='connections'),
    path('settings/', views.settings, name='settings'),
    path('admin/', admin.site.urls),
]
