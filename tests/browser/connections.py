"""Private demo CRUD and browser microphone checks; never contacts an AI provider."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

base = os.environ.get('AMPVE_BASE_URL', 'https://ampve.com').rstrip('/')
creds = json.loads(Path(os.environ.get('AMPVE_DEMO_CREDENTIALS', '/home/ampve/.config/ampve/demo-credentials.json')).read_text())['accounts'][0]
fixture = 'TEST-FIXTURE-NOT-A-REAL-API-KEY-0123456789'
label = 'Browser verification fixture'
Path('.browser-tests').mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'])
    context = browser.new_context(permissions=['microphone'], viewport={'width':1440,'height':1000})
    page = context.new_page()
    errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base + '/accounts/login/')
    page.get_by_label('Email address').fill(creds['email'])
    page.get_by_label('Password').fill(creds['password'])
    page.get_by_role('button', name='Sign in', exact=True).click()
    page.wait_for_url('**/home/')
    # Verify the real public WSS route refuses invalid grants without a provider call.
    refused = page.evaluate('''() => new Promise((resolve, reject) => {
      const ws = new WebSocket(`wss://${location.host}/audio/ws`);
      const timer = setTimeout(() => {ws.close();reject(new Error('WSS timeout'));},10000);
      ws.onopen = () => ws.send(JSON.stringify({ticket:'invalid-fixture-ticket'}));
      ws.onmessage = event => {clearTimeout(timer);resolve(JSON.parse(event.data).type);ws.close();};
      ws.onerror = () => {clearTimeout(timer);reject(new Error('WSS unavailable'));};
    })''')
    assert refused == 'error'
    created = False
    try:
        page.goto(base + '/connections/')
        page.get_by_label('Provider').select_option('openai')
        page.get_by_label('Connection name').fill(label)
        page.get_by_label('API key').fill(fixture)
        page.get_by_role('button', name='Save connection').click()
        page.get_by_text('Connection saved securely.', exact=False).wait_for()
        created = True
        card = page.locator('.connection-card').filter(has_text=label)
        assert fixture not in page.content()
        for width in [390,768,1440]:
            page.set_viewport_size({'width':width,'height':1000})
            page.wait_for_timeout(350)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
            page.screenshot(path=f'.browser-tests/connections-{width}.png',full_page=True)
        card.get_by_role('link',name='Replace key').click()
        page.get_by_label('API key').fill(fixture + '-REPLACED')
        page.get_by_role('button',name='Replace key',exact=True).click()
        page.get_by_text('API key replaced.',exact=False).wait_for()
        # Browser-only WebSocket fixture: real microphone capture/worklet, no network provider.
        packets = []
        def route(ws):
            def receive(message):
                if isinstance(message, str):
                    ws.send(json.dumps({'type':'ready','sample_rate':24000}))
                else:
                    packets.append(len(message))
                    if len(packets) == 1:
                        ws.send(message)
            ws.on_message(receive)
        page.route_web_socket('**/audio/ws', route)
        card.get_by_role('link',name='Try voice preview →').click()
        page.get_by_role('checkbox').check()
        page.get_by_role('button',name='Start voice preview').click()
        page.get_by_role('button',name='Mute microphone',exact=True).wait_for(state='visible')
        page.wait_for_function("!document.querySelector('.voice-mute').disabled")
        page.wait_for_timeout(500)
        assert packets and all(size == 960 for size in packets)
        page.get_by_role('button',name='Mute microphone',exact=True).click()
        assert page.get_by_role('button',name='Unmute microphone').get_attribute('aria-pressed') == 'true'
        page.get_by_role('button',name='Stop session').click()
        assert page.get_by_text('Session stopped. Microphone off.',exact=True).is_visible()
        assert page.get_by_role('button',name='Stop session').is_disabled()
        page.screenshot(path='.browser-tests/voice-stopped.png',full_page=True)
    finally:
        if created:
            page.goto(base + '/connections/')
            card = page.locator('.connection-card').filter(has_text=label)
            card.locator('summary').click()
            card.get_by_role('button',name='Delete connection',exact=True).click()
            page.get_by_text('Connection deleted.',exact=False).wait_for()
            assert page.locator('.connection-card').filter(has_text=label).count() == 0
        browser.close()
    assert not errors, errors
    print('Passed: public WSS rejection, connection CRUD, hidden key, 3 widths, fixture microphone PCM/mute/stop. No provider calls.')
