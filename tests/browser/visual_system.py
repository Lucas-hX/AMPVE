"""Cross-surface visual-system fixture; no server, device or production data."""
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

factory = RequestFactory()
visitor = NS(is_authenticated=False)
owner = NS(is_authenticated=True, first_name='Fixture', email='fixture@example.test', is_staff=False)
landing_request = factory.get('/', secure=True); landing_request.user = visitor
home_request = factory.get('/home/', secure=True); home_request.user = owner
pages = {
    '/': render_to_string('landing.html', request=landing_request),
    '/home/': render_to_string('workspace/home.html', {
        'title': 'Make room for more.', 'section': 'home', 'device_count': 1,
    }, request=home_request),
}

hero_exports = ROOT / 'images/ampve-brand-kit-v1/hero/exports'
assert (hero_exports / 'landing-devices-wide-v1.webp').stat().st_size < 100_000
assert (hero_exports / 'landing-devices-mobile-v1.webp').stat().st_size < 100_000

with sync_playwright() as playwright:
    launch = {}
    if os.environ.get('AMPVE_BROWSER_EXECUTABLE'):
        launch['executable_path'] = os.environ['AMPVE_BROWSER_EXECUTABLE']
    browser = playwright.chromium.launch(**launch)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    failed = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.on('response', lambda response: failed.append((response.status, response.url)) if response.status >= 400 else None)

    def route(request_route):
        path = urlparse(request_route.request.url).path
        if path in pages:
            request_route.fulfill(status=200, content_type='text/html', body=pages[path]); return
        if path.startswith('/static/'):
            file = finders.find(path[len('/static/'):].replace('/', os.sep))
            if file:
                request_route.fulfill(
                    status=200,
                    content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream',
                    body=Path(file).read_bytes(),
                ); return
        request_route.fulfill(status=404, body='')

    page.route('https://ampve.test/**', route)
    output = ROOT / '.browser-tests'; output.mkdir(exist_ok=True)

    for width in [390, 768, 1440]:
        page.set_viewport_size({'width': width, 'height': 1000})
        page.goto('https://ampve.test/')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, 'landing')
        assert page.locator('.hero-visual[role="img"][aria-label]').count() == 1
        assert page.locator('.hero-device-picture img').evaluate('image => image.complete && image.naturalWidth > 0')
        expected_export = 'landing-devices-mobile-v1.webp' if width <= 700 else 'landing-devices-wide-v1.webp'
        assert page.locator('.hero-device-picture img').evaluate('image => image.currentSrc').endswith(expected_export)
        page.screenshot(path=output / f'visual-system-landing-{width}.png', full_page=True)

        page.goto('https://ampve.test/home/')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, 'home')
        assert page.locator('svg.ampve-icon use').count() >= 6
        page.screenshot(path=output / f'visual-system-home-{width}.png', full_page=True)

    page.set_viewport_size({'width': 390, 'height': 900})
    page.goto('https://ampve.test/home/')
    page.locator('.menu-toggle').click()
    assert page.locator('.sidebar').get_attribute('aria-modal') == 'true'
    assert page.get_by_role('button', name='Close menu').evaluate('node => node === document.activeElement')
    page.keyboard.press('Escape')
    assert page.locator('.menu-toggle').get_attribute('aria-expanded') == 'false'

    page.goto('https://ampve.test/')
    page.keyboard.press('Tab')
    assert page.locator('.skip').evaluate('node => node === document.activeElement')
    assert page.locator('.skip').evaluate("node => getComputedStyle(node).outlineStyle") != 'none'
    page.emulate_media(reduced_motion='reduce')
    assert page.locator('.hero-device-picture img').evaluate("node => getComputedStyle(node).animationName") == 'none'
    assert page.locator('.hero-ribbon').evaluate("node => getComputedStyle(node).animationName") == 'none'

    assert not failed, failed
    assert not errors, errors
    browser.close()

print('Visual system fixture passed landing and Home at three widths with optimized hero exports, keyboard focus, mobile navigation and reduced motion.')
