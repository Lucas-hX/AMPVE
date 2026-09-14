"""Rendered visual-console browser fixture; no server, device or production data."""
import json
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
from playwright.sync_api import sync_playwright

device_id=uuid.uuid4();session_id=uuid.uuid4();state_page='home';commands=[]
request=RequestFactory().get(f'/devices/{device_id}/console/',secure=True)
request.user=NS(first_name='Fixture',email='fixture@example.test',is_staff=False)
device=NS(pk=device_id,name='Studio display',connection_state='Online',firmware_version='fixture-console')
html=render_to_string('workspace/device_console.html',{'title':'Studio display console','section':'devices','device':device},request=request)

with sync_playwright() as p:
    launch={}
    if os.environ.get('AMPVE_BROWSER_EXECUTABLE'):launch['executable_path']=os.environ['AMPVE_BROWSER_EXECUTABLE']
    browser=p.chromium.launch(**launch);context=browser.new_context(has_touch=True,viewport={'width':1440,'height':1000})
    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    def route(r):
        global state_page
        req=r.request;path=urlparse(req.url).path
        if path==f'/devices/{device_id}/console/':r.fulfill(status=200,content_type='text/html',body=html);return
        if path.startswith('/static/'):
            file=finders.find(path[len('/static/'):].replace('/',os.sep))
            if file:r.fulfill(status=200,content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream',body=Path(file).read_bytes());return
        if path==f'/devices/{device_id}/console/session/' and req.method=='POST':
            payload={'protocol':1,'session_id':str(session_id),'expires_at':'2030-01-01T00:10:00Z','poll_interval_ms':800,
                'device':{'id':str(device_id),'name':'Studio display','connection':'Online','firmware_version':'fixture-console'},
                'screen':{'revision':1,'page':state_page,'display_mode':'physical','remote_allowed':True,'updated_at':'2030-01-01T00:00:00Z'},
                'last_command':{'id':None,'result':None}}
            r.fulfill(status=201,content_type='application/json',body=json.dumps(payload));return
        if path==f'/devices/{device_id}/console/session/{session_id}/' and req.method=='GET':
            payload={'protocol':1,'active':True,'expires_at':'2030-01-01T00:10:00Z','device_connected':True,
                'device':{'id':str(device_id),'name':'Studio display','connection':'Online','firmware_version':'fixture-console'},
                'screen':{'revision':len(commands)+1,'page':state_page,'display_mode':'physical','remote_allowed':True,'updated_at':'2030-01-01T00:00:01Z'},
                'last_command':{'id':str(uuid.uuid5(uuid.NAMESPACE_URL,str(len(commands)))) if commands else None,'result':'applied' if commands else None}}
            r.fulfill(status=200,content_type='application/json',body=json.dumps(payload));return
        if path.endswith('/commands/') and req.method=='POST':
            payload=req.post_data_json
            if payload['target']=='cancel_update':
                r.fulfill(status=409,content_type='application/json',body='{"error":"Rejected fixture input."}');return
            commands.append(payload)
            if payload['target'] in {'home','wifi','device','settings','companion'}:state_page=payload['target']
            r.fulfill(status=202,content_type='application/json',body=json.dumps({'protocol':1,'command_id':str(uuid.uuid4()),'state':'pending'}));return
        if path.endswith('/stop/') and req.method=='POST':
            r.fulfill(status=200,content_type='application/json',body='{"protocol":1,"active":false}');return
        r.fulfill(status=404,body='')
    page.route('https://ampve.test/**',route)
    page.goto(f'https://ampve.test/devices/{device_id}/console/')
    assert page.get_by_role('heading',name='Reach it from here.').is_visible()
    assert page.get_by_text('No video, microphone stream, terminal or unrestricted code').is_visible()
    assert page.locator('.hud-signal').count()==5
    assert page.get_by_text('Always available',exact=True).is_visible()
    page.get_by_role('button',name='Start 10-minute session').click()
    page.wait_for_function("document.querySelector('[data-console-status]').textContent.includes('Live device channel')")
    page.wait_for_function("document.querySelector('[data-hud=channel]').dataset.state==='live'")
    assert page.get_by_role('button',name='Start 10-minute session').is_hidden()
    assert page.get_by_role('button',name='Stop remote session').is_visible()
    page.locator('.console-dock [data-console-target="settings"]').click()
    page.wait_for_function("document.querySelector('[data-page=settings]').hidden===false")
    page.wait_for_function("document.querySelector('[data-hud-input]').textContent.includes('applied')")
    page.locator('[data-page=settings] [data-console-target="cancel_update"]').click()
    page.wait_for_function("document.querySelector('[data-hud=input]').dataset.state==='rejected'")
    page.locator('[data-page=settings] [data-console-target="mute"]').tap()
    page.locator('.console-frame').press('h')
    page.wait_for_function("document.querySelector('[data-page=home]').hidden===false")
    assert commands[0]['input_source'] in {'mouse','touch'} and commands[0]['target']=='settings'
    assert commands[1]['input_source']=='touch' and commands[1]['target']=='mute'
    assert commands[2]['input_source']=='keyboard' and commands[2]['target']=='home'
    for command in commands[:2]:assert 0<=command['x']<=1023 and 0<=command['y']<=599
    page.emulate_media(reduced_motion='reduce')
    page.locator('[data-hud="input"]').evaluate("node=>node.classList.add('is-acknowledged')")
    assert page.locator('[data-hud="input"]').evaluate("node=>getComputedStyle(node).animationName")=='none'
    page.emulate_media(reduced_motion='no-preference')
    output=ROOT/'.browser-tests';output.mkdir(exist_ok=True)
    for width in [390,768,1440]:
        page.set_viewport_size({'width':width,'height':1000})
        page.wait_for_timeout(250)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        page.screenshot(path=output/f'console-{width}.png',full_page=True)
    page.get_by_role('button',name='Stop remote session').click()
    page.get_by_role('button',name='Start 10-minute session').wait_for(state='visible')
    assert not errors,errors
    browser.close()
print('Visual-console fixture passed at three widths with mouse/touch, keyboard, bounded coordinates and stop. No hardware tested.')
