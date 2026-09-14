"""Rendered My devices fixture; no server, device or production data."""
import mimetypes
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import uuid
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/platform'))
os.environ['AMPVE_TESTING'] = '1'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import RequestFactory
from playwright.sync_api import sync_playwright

request = RequestFactory().get('/devices/', secure=True)
request.user = NS(first_name='Fixture', email='fixture@example.test', is_staff=False)
now = datetime.now(timezone.utc)
devices = [
    NS(pk=uuid.uuid4(), name='Studio display', connection_state='Online',
       last_seen=now-timedelta(seconds=34), hardware_profile='waveshare-esp32-p4-wifi6-touch-lcd-7b',
       transport='wifi', firmware_version='fixture-online'),
    NS(pk=uuid.uuid4(), name='Kitchen companion', connection_state='Offline',
       last_seen=now-timedelta(minutes=8), hardware_profile='waveshare-esp32-p4-wifi6-touch-lcd-7b',
       transport='wifi', firmware_version='fixture-offline'),
    NS(pk=uuid.uuid4(), name='New workspace device', connection_state='Awaiting device',
       last_seen=None, hardware_profile='waveshare-esp32-p4-wifi6-touch-lcd-7b',
       transport='', firmware_version=''),
]
html = render_to_string('workspace/devices.html', {
    'title':'Your devices. Your space.', 'section':'devices', 'devices':devices,
    'hardware_name':'Waveshare ESP32-P4-WIFI6 Touch LCD 7B'}, request=request)

with sync_playwright() as playwright:
    launch = {}
    if os.environ.get('AMPVE_BROWSER_EXECUTABLE'):
        launch['executable_path'] = os.environ['AMPVE_BROWSER_EXECUTABLE']
    browser = playwright.chromium.launch(**launch)
    page = browser.new_page(viewport={'width':1440, 'height':1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)

    def route(r):
        path = urlparse(r.request.url).path
        if path == '/devices/':
            r.fulfill(status=200, content_type='text/html', body=html);return
        if path.startswith('/static/'):
            file = finders.find(path[len('/static/'):].replace('/', os.sep))
            if file:
                r.fulfill(status=200, content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream',
                          body=Path(file).read_bytes());return
        r.fulfill(status=404, body='')

    page.route('https://ampve.test/**', route)
    page.goto('https://ampve.test/devices/')
    assert page.locator('.device-card').count() == 3
    assert page.get_by_text('No application assigned', exact=True).count() == 3
    assert page.locator('time[datetime][aria-label^="Last contact"]').count() == 2
    page.locator('.device-card').first.locator('summary').click()
    assert page.get_by_text('waveshare-esp32-p4-wifi6-touch-lcd-7b', exact=True).first.is_visible()
    output = ROOT / '.browser-tests';output.mkdir(exist_ok=True)
    for width in [390, 768, 1440]:
        page.set_viewport_size({'width':width, 'height':1000});page.wait_for_timeout(350)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        page.screenshot(path=output / f'device-cards-{width}.png', full_page=True)
    assert not errors, errors
    browser.close()

print('My devices fixture passed at three widths with truthful states, exact timestamps and progressive disclosure. No hardware tested.')
