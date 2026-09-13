"""Authenticated curated firmware delivery; never accept private device dumps."""
import hashlib
import json
from pathlib import Path
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from .release_contract import read_release


def release_data(recovery=False):
    recovery_root=settings.FIRMWARE_RECOVERY_ROOT if recovery else ''
    root=Path(recovery_root or settings.FIRMWARE_RELEASE_ROOT)
    if (root/'approved-release.json').exists():
        try:
            policy,release_id,key,envelope,floor=read_release(root,Path(settings.FIRMWARE_PUBLISHER_TRUST))
            if policy['purpose']!='initial-install':
                return {'status':'ota-release-only','installable':False},None
            return {'status':'reviewed-development-release','envelope':envelope,'publisher_key':key,
                    'release_id':release_id,'minimum_sequence':floor,'release':policy},root
        except Exception:
            # Missing trust, revocation and corrupt provenance all disable new operations.
            return {'status':'release-verification-failed','installable':False},None
    if recovery_root:
        return {'status':'release-verification-failed','installable':False},None
    try:
        review=Path(settings.FIRMWARE_REVIEW_ROOT)
        manifest=json.loads((review/'review-manifest.json').read_text())
        if manifest.get('installation_profile')!='waveshare-7b-stock-v1':raise ValueError()
        app=next(a for a in manifest['proposed_regions_not_approved_writes'] if a['file']=='xiaozhi.bin')
        return {'status':'development-review','installable':False,'profile':manifest['installation_profile'],
            'commissioning':manifest.get('commissioning','network-first-v1'),
            'app':{'size':app['size'],'sha256':app['sha256'],'offset':app['offset']},
            'remaining':['Stock bootloader and C6 compatibility review','Exact local write/recovery plan and approval','Physical first-boot and recovery validation']},review
    except (OSError,ValueError,KeyError,StopIteration):
        return {'status':'no-reviewed-release','installable':False},None


@never_cache
@login_required
@require_GET
def release(request):
    data,_=release_data(recovery=request.GET.get('recovery')=='1')
    return JsonResponse(data)


@never_cache
@login_required
@require_GET
def artifact(request, digest):
    data,root=release_data(recovery=request.GET.get('recovery')=='1')
    app=data.get('app') or data.get('release',{}).get('app',{})
    if root is None or digest!=app.get('sha256'):raise Http404()
    # Only the app is deliverable here. No arbitrary path or private audit upload/download.
    path=root/'xiaozhi.bin'
    try:
        content=path.read_bytes()
    except OSError:raise Http404() from None
    if len(content)!=app.get('size') or hashlib.sha256(content).hexdigest()!=digest:raise Http404()
    from io import BytesIO
    response=FileResponse(BytesIO(content),as_attachment=True,filename='ampve-'+digest[:12]+'.bin',content_type='application/octet-stream')
    response['X-Content-Type-Options']='nosniff'
    return response


@never_cache
@login_required
@require_GET
def review_bundle(request):
    data,root=release_data()
    if data.get('status')!='development-review' or root is None:raise Http404()
    path=root.parent/(root.name+'.zip')
    try:stream=path.open('rb')
    except OSError:raise Http404() from None
    return FileResponse(stream,as_attachment=True,filename='ampve-stock-profile-review.zip',content_type='application/zip')
