"""Rendered onboarding visual fixture; no serial, flash, server or production data."""
import mimetypes
import os
from pathlib import Path
from types import SimpleNamespace as NS
import sys
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
from workspace.forms import ClaimDeviceForm

request = RequestFactory().get('/devices/add/', secure=True)
request.user = NS(first_name='Fixture', email='fixture@example.test', is_staff=False)
html = render_to_string('workspace/onboarding.html', {
    'title':'Bring your device.', 'section':'devices', 'form':ClaimDeviceForm(),
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
        if path == '/devices/add/':
            r.fulfill(status=200, content_type='text/html', body=html);return
        if path == '/static/workspace/onboarding.bundle.js':
            r.fulfill(status=204, content_type='application/javascript', body='');return
        if path.startswith('/static/'):
            file = finders.find(path[len('/static/'):].replace('/', os.sep))
            if file:
                r.fulfill(status=200, content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream',
                          body=Path(file).read_bytes());return
        r.fulfill(status=404, body='')

    page.route('https://ampve.test/**', route)
    page.goto('https://ampve.test/devices/add/')
    assert page.locator('.onboarding-intro-art img').evaluate('image=>image.naturalWidth>0')
    assert page.locator('[role="status"]').count() >= 7
    root = page.locator('#firmware-setup')
    root.evaluate("node=>node.dataset.setupState='working'")
    assert page.locator('#setup-visual-label').is_visible()
    page.emulate_media(reduced_motion='reduce')
    assert page.locator('.setup-state-icon').evaluate("node=>getComputedStyle(node).animationName") == 'none'
    page.emulate_media(reduced_motion='no-preference')
    root.evaluate("node=>node.dataset.setupState='success'")
    page.locator('#setup-visual-label').evaluate("node=>node.textContent='AMPVE core confirmed'")
    page.locator('#setup-success-visual').evaluate('node=>node.hidden=false')
    page.locator('#restore-panel').evaluate('node=>node.hidden=false')
    assert page.locator('#setup-success-visual img').evaluate('image=>image.naturalWidth>0')
    assert page.locator('#restore-panel img').evaluate('image=>image.naturalWidth>0')
    output = ROOT / '.browser-tests';output.mkdir(exist_ok=True)
    for width in [390, 768, 1440]:
        page.set_viewport_size({'width':width, 'height':1000});page.wait_for_timeout(350)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        page.screenshot(path=output / f'onboarding-assets-{width}.png', full_page=True)
    assert not errors, errors
    browser.close()

print('Onboarding visual fixture passed at three widths with SVG assets, visible status regions and reduced motion. No hardware tested.')
