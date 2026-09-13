"""Render update states with isolated fixtures; no server, device or release mutations."""
import mimetypes
import os
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import uuid
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'apps/platform'))
os.environ['AMPVE_TESTING']='1';os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import timezone
from workspace.models import FirmwareDeployment
from playwright.sync_api import sync_playwright

request=RequestFactory().get('/fixture/',secure=True)
request.user=NS(first_name='Fixture',email='fixture@example.test',is_staff=False)
device=NS(pk=uuid.uuid4(),name='Synthetic update fixture',connection_state='Offline')
release=NS(release_notes='Fixture improvements\n<script>literal notes only</script>',pk='a'*64,sequence=2,policy={'firmware_version':'fixture-2','app':{'size':131072,'sha256':'b'*64},'ota_review':'Fixture recovery review <literal text>','expires_at':'2030-01-01T00:00:00Z'})
with sync_playwright() as p:
    browser=p.chromium.launch();page=browser.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    def route(r):
        path=urlparse(r.request.url).path
        if path.startswith('/static/'):
            file=finders.find(path[len('/static/'):])
            if file:r.fulfill(status=200,content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream',body=Path(file).read_bytes());return
        r.fulfill(status=404,body='')
    page.route('https://ampve.test/**',route)
    for state,_ in FirmwareDeployment.STATES:
        active=state in FirmwareDeployment.ACTIVE
        job=NS(pk=uuid.uuid4(),state=state,release=release,bytes_written=131072,needs_attention=state=='rebooting',created_at=timezone.now(),updated_at=timezone.now(),failure_message='The network connection was interrupted.' if state=='failed' else '',get_state_display=lambda state=state:state.replace('_',' ').capitalize())
        html=render_to_string('workspace/device_updates.html',dict(title='Update fixture',section='devices',device=device,confirmed=NS(release=release,confirmed_sequence=1),pending=active,releases=[release],request_key=uuid.uuid4(),availability='Fixture status',deployments=[job]),request=request)
        def fixture_route(r):
            r.fulfill(status=200,content_type='text/html',body=html)
        page.route('https://ampve.test/fixture/',fixture_route)
        page.goto('https://ampve.test/fixture/')
        assert page.get_by_role('button',name='Queue firmware update').count()==(0 if active else 1)
        assert page.get_by_role('button',name='Cancel queued update').count()==(1 if state=='queued' else 0)
        page.locator('details summary').click()
        assert '<literal text>' in page.locator('details').inner_text()
        assert '<script>literal notes only</script>' in page.locator('details').inner_text()
        assert page.locator('details script').count()==0
        for width in [390,768,1440]:
            page.set_viewport_size({'width':width,'height':950})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(state,width)
        if state=='rebooting':assert 'Waiting for a confirmed startup' in page.locator('main').inner_text()
        page.unroute('https://ampve.test/fixture/')
    assert not errors,errors
    browser.close()
print('Eight rendered update-state fixtures passed at three widths: release details, pending controls and literal review text. No hardware tested.')
