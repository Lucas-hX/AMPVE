"""Private-instance software fixture. No USB, flash or provider calls occur."""
import json
import os
import secrets
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/platform'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from workspace.models import Device, DeviceEnrollment
from workspace.hardware_profiles import CONTRACT
from playwright.sync_api import sync_playwright

base='https://ampve.com'
creds=json.loads(Path('/home/ampve/.config/ampve/demo-credentials.json').read_text())['accounts'][0]
label='Temporary browser device fixture'
credential=secrets.token_urlsafe(32)
enrollment_id=None;device_id=None
with sync_playwright() as p:
    browser=p.chromium.launch()
    context=browser.new_context(viewport={'width':1440,'height':1000})
    # Web Serial selection fixture only; any attempt to open hardware throws.
    context.add_init_script('''Object.defineProperty(navigator, 'serial', {value:{
      requestPort:async()=>({getInfo:()=>({usbVendorId:0x303a,usbProductId:0x1001}),open:()=>{throw Error('No physical port in this fixture');}}),
      addEventListener:()=>{}
    }});''')
    page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    try:
        page.goto(base+'/accounts/login/')
        page.get_by_label('Email address').fill(creds['email'])
        page.get_by_label('Password').fill(creds['password'])
        page.get_by_role('button',name='Sign in',exact=True).click()
        page.wait_for_url('**/home/')
        page.goto(base+'/devices/add/')
        page.get_by_role('button',name='Select a USB serial port').click()
        page.get_by_text('Confirm the printed 7B label.',exact=False).wait_for()
        assert 'this step does not write flash' in page.content()
        for width in [390,768,1440]:
            page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(350)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
            page.screenshot(path=f'.browser-tests/onboarding-{width}.png',full_page=True)
        ticket_response=context.request.post(base+'/api/devices/v1/enroll/',data={'protocol':1,'hardware_profile':'waveshare-esp32-p4-wifi6-touch-lcd-7b'})
        assert ticket_response.status==201
        ticket=ticket_response.json();enrollment_id=ticket['enrollment_id']
        page.get_by_label('Pairing code').fill(ticket['code'])
        page.get_by_label('Device name').fill(label)
        page.get_by_label('I can see this code').check()
        page.get_by_role('button',name='Add my device',exact=True).click()
        page.get_by_text('Awaiting device',exact=True).wait_for()
        exchange=context.request.post(base+f'/api/devices/v1/enroll/{enrollment_id}/exchange/',
            data={'credential':credential},headers={'Authorization':'Bearer '+ticket['bootstrap_proof']})
        assert exchange.status==200
        device_id=exchange.json()['device_id']
        heartbeat={'protocol':1,'firmware_version':'software-fixture','chip_revision':'1.3','transport':'wifi','acknowledged_version':0}
        heartbeat['hardware_report']={'schema':2,'compatibility':CONTRACT,'flash_bytes':33554432,'psram_bytes':None,
            'display':{'width':1024,'height':600},'capabilities':{
                'display':'initialized','touch':'configured','speaker':'configured',
                'microphone':'unknown','wifi':'passed'}}
        reply=context.request.post(base+f'/api/devices/v1/{device_id}/heartbeat/',data=heartbeat,headers={'Authorization':'Bearer '+credential})
        assert reply.status==200
        page.reload();page.get_by_text('Online',exact=True).wait_for()
        assert page.get_by_text('Driver initialized',exact=False).is_visible()
        assert page.get_by_text('Not checked',exact=False).is_visible()
        assert page.get_by_text('Not reported',exact=True).is_visible()
        page.get_by_text('Firmware compatibility checks',exact=True).click()
        assert page.get_by_text('Compatibility with the installed ESP32-C6 firmware still needs review.',exact=True).is_visible()
        assert page.get_by_text('The required 32 MiB initialized PSRAM has not been reported.',exact=True).is_visible()
        page.get_by_label('Speaker volume').fill('45')
        page.get_by_role('button',name='Save device settings').click()
        page.get_by_text('Settings saved.',exact=False).wait_for()
        assert page.get_by_text('0 · Pending',exact=False).is_visible()
        for width in [390,768,1440]:
            page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(350)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
            page.screenshot(path=f'.browser-tests/device-{width}.png',full_page=True)
        page.get_by_role('link',name='View firmware updates',exact=True).click()
        page.get_by_text('No confirmed firmware image has been reported.',exact=False).wait_for()
        for width in [390,768,1440]:
            page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(350)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
            page.screenshot(path=f'.browser-tests/device-updates-{width}.png',full_page=True)
        page.goto(base+f'/devices/{device_id}/')
        page.get_by_role('button',name='Revoke device access',exact=True).click()
        page.get_by_text('Revoked',exact=True).wait_for()
        rejected=context.request.post(base+f'/api/devices/v1/{device_id}/heartbeat/',data=heartbeat,headers={'Authorization':'Bearer '+credential})
        assert rejected.status==401
        assert not errors,errors
        print('Public software-fixture flow passed: USB selector, claim, exchange, heartbeat, settings pending, firmware update empty state, revocation, three widths. No hardware validation.')
    finally:
        browser.close()
        def cleanup():
            if enrollment_id:
                row=DeviceEnrollment.objects.filter(pk=enrollment_id).first()
                if row and row.device_id:
                    Device.objects.filter(pk=row.device_id,name=label,owner__email=creds['email']).delete()
                DeviceEnrollment.objects.filter(pk=enrollment_id).delete()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(cleanup).result()
