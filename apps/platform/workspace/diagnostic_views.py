"""Authenticated curated RAM diagnostics, separate from installation releases."""
import hashlib
import json
from pathlib import Path
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


def read_probe():
    root=Path(settings.C6_PROBE_ROOT)
    metadata=root/'manifest.json'
    if metadata.stat().st_size>4096:raise ValueError('Invalid probe metadata')
    manifest=json.loads(metadata.read_bytes())
    if (not isinstance(manifest,dict) or type(manifest.get('schema')) is not int or manifest.get('schema')!=1 or manifest.get('kind')!='ampve-c6-ram-probe' or
            manifest.get('flash_writes') is not False or manifest.get('chip_revision')!=103 or
            type(manifest.get('size')) is not int or not 24<=manifest['size']<=768*1024):
        raise ValueError('Invalid RAM probe')
    artifact=root/'probe.bin'
    if artifact.stat().st_size!=manifest['size']:raise ValueError('Probe size mismatch')
    data=artifact.read_bytes()
    if hashlib.sha256(data).hexdigest()!=manifest.get('sha256'):raise ValueError('Probe hash mismatch')
    return manifest,data


@never_cache
@login_required
@require_GET
def c6_probe(request):
    try:manifest,data=read_probe()
    except (OSError,ValueError,KeyError):raise Http404() from None
    if request.GET.get('artifact')=='1':
        response=HttpResponse(data,content_type='application/octet-stream')
        response['X-Content-Type-Options']='nosniff'
        return response
    return JsonResponse(manifest)
