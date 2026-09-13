"""Browser-only fixtures for the patched local portal; never opens a device connection."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--component', type=Path, required=True)
component = parser.parse_args().component
with sync_playwright() as browser_api:
    browser = browser_api.chromium.launch(headless=True)
    page = browser.new_page()
    calls, errors = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def route_request(route):
        request = route.request
        url = urlparse(request.url)
        if url.netloc != '192.168.4.1':
            return route.abort()
        if url.path == '/':
            return route.fulfill(content_type='text/html', body=(component/'assets/wifi_configuration.html').read_text())
        calls.append((url.path, request.headers.get('x-ampve-setup')))
        if url.path in ['/saved/delete', '/saved/set_default']:
            return route.fulfill(status=500, content_type='text/plain', body='Intentional storage failure')
        if url.path == '/saved/list':
            data = ['Fixture Wi-Fi', '<img src=x onerror="window.ssidInjected=true">']
        elif url.path == '/scan':
            data = {'support_5g': False, 'aps': []}
        elif url.path == '/advanced/config':
            data = {'language': 'en-US', 'show_ota_config': False, 'show_sleep_config': False}
        else:
            data = {'success': False, 'error': 'Intentional offline fixture'}
        route.fulfill(content_type='application/json', body=json.dumps(data))
    page.route('**/*', route_request)
    page.goto('http://192.168.4.1/')
    page.get_by_text('<img src=x onerror="window.ssidInjected=true">', exact=True).wait_for()
    assert page.evaluate('window.ssidInjected === undefined')
    for endpoint, selector in [('/saved/delete', '[onclick^="deleteItem"]'), ('/saved/set_default', '[onclick^="setDefaultItem"]')]:
        control = page.locator(selector).first
        with page.expect_response(lambda response: urlparse(response.url).path == endpoint) as outcome:
            control.click()
        assert outcome.value.status == 500
        page.wait_for_function("document.getElementById('toast').textContent.includes('were not saved')")
        page.wait_for_function("selector => !document.querySelector(selector).disabled", arg=selector)
        assert page.locator('#saved_list li').count() == 2
    page.locator('#ssid').evaluate('(element) => {element.removeAttribute("readonly");element.value="Fixture Wi-Fi";}')
    page.locator('#password').fill('fixture-only-password')
    page.locator('#button').click()
    page.get_by_text('Intentional offline fixture', exact=True).wait_for()
    assert page.locator('#password').input_value() == ''
    assert calls and all(header == '1' for _, header in calls), calls
    assert not errors, errors
    browser.close()
print('Portal fixtures passed: SSID rendered as text, API requests carry the CSRF header, password widget clears, failed saved-network updates stay visible and controls recover.')
