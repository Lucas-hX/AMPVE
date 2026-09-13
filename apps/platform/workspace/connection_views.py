from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from .audio_auth import issue_grant
from .credentials import encrypt_key
from .forms import ConnectionForm, ReplaceKeyForm
from .models import ProviderConnection, User
from .provider_config import PROVIDERS, RESULTS


@never_cache
@login_required
@sensitive_post_parameters('api_key')
def connections(request):
    form = ConnectionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            if ProviderConnection.objects.filter(owner=request.user).count() >= 10:
                form.add_error(None, 'This private workspace supports up to 10 connections.')
            else:
                item = ProviderConnection(owner=request.user, provider=form.cleaned_data['provider'], label=form.cleaned_data['label'])
                item.encrypted_key = encrypt_key(item, form.cleaned_data['api_key'])
                item.save()
                messages.success(request, 'Connection saved securely. Run a connection test when you are ready.')
                return redirect('connections')
    items = list(ProviderConnection.objects.filter(owner=request.user).defer('encrypted_key'))
    for item in items:
        item.preset = PROVIDERS[item.provider]
        item.result_message = RESULTS.get(item.result_code, 'Not tested yet.')
    return render(request, 'workspace/connections.html', {'form': form, 'connections': items,
        'section': 'connections', 'title': 'Your AI connections.'})


@never_cache
@login_required
@sensitive_post_parameters('api_key')
def replace_key(request, pk):
    item = get_object_or_404(ProviderConnection.objects.defer('encrypted_key'), pk=pk, owner=request.user)
    form = ReplaceKeyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            item = get_object_or_404(ProviderConnection.objects.select_for_update(), pk=pk, owner=request.user)
            item.encrypted_key = encrypt_key(item, form.cleaned_data['api_key'])
            item.revision += 1
            item.validation, item.result_code, item.checked_at = 'untested', '', None
            item.save()
        messages.success(request, 'API key replaced. Previous audio sessions will stop within two seconds.')
        return redirect('connections')
    return render(request, 'workspace/replace_key.html', {'form': form, 'connection': item,
        'section': 'connections', 'title': 'Replace your API key.'})


@never_cache
@login_required
@require_POST
def delete_connection(request, pk):
    with transaction.atomic():
        item = get_object_or_404(ProviderConnection.objects.select_for_update(), pk=pk, owner=request.user)
        item.delete()
    messages.success(request, 'Connection deleted. Active audio sessions will stop within two seconds.')
    return redirect('connections')


@never_cache
@login_required
def voice_preview(request, pk):
    item = get_object_or_404(ProviderConnection.objects.defer('encrypted_key'), pk=pk, owner=request.user)
    return render(request, 'workspace/voice.html', {'connection': item, 'preset': PROVIDERS[item.provider],
        'section': 'connections', 'title': 'Say hello to Companion.'})


@never_cache
@login_required
@require_POST
def audio_ticket(request, pk):
    mode = request.POST.get('mode')
    if mode not in ('check', 'voice') or request.POST.get('consent') != 'yes':
        return JsonResponse({'error': 'Confirm the API usage notice before starting.'}, status=400)
    get_object_or_404(ProviderConnection, pk=pk, owner=request.user)
    try:
        token = issue_grant(request.user, pk, request.session.session_key, mode)
    except ProviderConnection.DoesNotExist:
        return JsonResponse({'error': 'Connection no longer exists.'}, status=404)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=429)
    return JsonResponse({'ticket': token, 'path': '/audio/ws', 'expires_in': 30})
