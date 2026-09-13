from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.http import JsonResponse
from .forms import ProfileForm, SignInForm
from .models import Application


class SignInView(LoginView):
    template_name = 'registration/login.html'
    authentication_form = SignInForm
    redirect_authenticated_user = True


@require_GET
def landing(request):
    return render(request, 'landing.html')


@never_cache
@login_required
def page(request, section='home'):
    titles = {'home': 'Make room for more.', 'devices': 'Your devices. Your space.',
              'apps': 'Find a little possibility.', 'connections': 'Your AI connections.',
              'onboarding': 'A new home for your ideas.'}
    return render(request, f'workspace/{section}.html', {'section': section,
        'title': titles[section], 'applications': Application.objects.all()})


@never_cache
@login_required
def settings(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your profile has been updated.')
        return redirect('settings')
    return render(request, 'workspace/settings.html', {'form': form, 'section': 'settings', 'title': 'Make it yours.'})


@require_GET
def health(request):
    return JsonResponse({'status': 'ok', 'service': 'ampve-platform'})
