"""Read-only browser check of the simulated on-device interface."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

creds=json.loads(Path('/home/ampve/.config/ampve/demo-credentials.json').read_text())['accounts'][0]
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('https://ampve.com/accounts/login/')
    page.get_by_label('Email address').fill(creds['email'])
    page.get_by_label('Password').fill(creds['password'])
    page.get_by_role('button',name='Sign in',exact=True).click()
    page.wait_for_url('**/home/')
    page.goto('https://ampve.com/devices/interface-preview/')
    page.wait_for_load_state('networkidle')
    assert page.get_by_text('Interactive concept · simulated states').is_visible()
    shell=page.locator('.runtime-shell')
    requests=[]
    page.on('request',lambda request:requests.append(request.method))
    for width in [390,768,1440]:
        page.set_viewport_size({'width':width,'height':1100})
        page.wait_for_timeout(350)
        for screen in ['home','wifi','about','settings','companion']:
            shell.locator('.runtime-nav [data-screen=home]').click()
            if screen!='home':
                shell.locator('[data-screen='+screen+']').click()
            assert shell.locator('[data-panel='+screen+']').is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(width,screen)
        shell.locator('.runtime-nav [data-screen=home]').click()
        page.screenshot(path=f'.browser-tests/runtime-home-{width}.png',full_page=True)
    shell.locator('[data-screen=wifi]').click()
    shell.locator('#runtime-connect').click()
    assert shell.get_by_text('Connection simulated.',exact=False).is_visible()
    shell.locator('.runtime-nav [data-screen=home]').click()
    shell.locator('[data-screen=about]').click()
    shell.get_by_role('button',name='Preview speaker check').click()
    assert shell.get_by_text('This preview does not play audio',exact=False).is_visible()
    shell.locator('#runtime-mute').click()
    assert shell.locator('#runtime-mute').get_attribute('aria-pressed')=='false'
    assert not requests,requests
    assert not errors,errors
    print('Runtime concept passed: five screens, three widths, local simulated controls, no network requests during interactions.')
    browser.close()
