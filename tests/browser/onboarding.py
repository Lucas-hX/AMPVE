"""Local rendered-template browser fixtures. No server writes, USB or provider calls."""
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
import hashlib
import json
import mimetypes
import os
import struct
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'apps/platform'))
os.environ['AMPVE_TESTING']='1'
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import RequestFactory
from workspace.forms import ClaimDeviceForm
from playwright.sync_api import sync_playwright


def image():
    data=bytearray(80)
    data[0]=0xe9;data[1]=1;data[23]=1
    struct.pack_into('<H',data,12,18)
    struct.pack_into('<HH',data,15,100,199)
    struct.pack_into('<II',data,24,0x4ff00000,32)
    data[79]=0xef
    return data+hashlib.sha256(data).digest()


def backup():
    entries=[('nvsfactory',1,2,0x9000,0x32000),('nvs',1,2,0x3b000,0xd2000),('otadata',1,0,0x10d000,0x2000),('phy_init',1,1,0x10f000,0x1000),('factory',0,0,0x110000,0x900000),('ota_0',0,16,0xa10000,0x3f0000),('ota_1',0,17,0xe00000,0x3f0000),('assets',1,130,0x11f0000,0x900000),('storage',1,130,0x1af0000,0x500000)]
    raw=b''.join(struct.pack('<HBBII16sI',0x50aa,t,s,o,z,n.encode(),0) for n,t,s,o,z in entries)
    table=raw+b'\xeb\xeb'+b'\xff'*14+hashlib.md5(raw).digest()
    data=bytearray(b'\xff'*(32*1024*1024));data[0x8000:0x8000+len(table)]=table
    for offset in [0x2000,0x110000,0xa10000]:data[offset:offset+len(image())]=image()
    return data

request=RequestFactory().get('/devices/add/',secure=True)
request.user=SimpleNamespace(first_name='Fixture',email='fixture@example.test',is_staff=False)
html=render_to_string('workspace/onboarding.html',{'title':'Bring your device.','section':'devices','hardware_name':'Waveshare ESP32-P4-WIFI6-Touch-LCD-7B','form':ClaimDeviceForm()},request=request)
with tempfile.TemporaryDirectory(prefix='ampve-browser-fixture-') as directory,sync_playwright() as p:
    root=Path(directory);data=backup();digest=hashlib.sha256(data).hexdigest()
    for name in ['backup-a.bin','backup-b.bin']:(root/name).write_bytes(data)
    (root/'audit-private.json').write_text(json.dumps({'independent_reads_match':True,'sha256':digest,'hardware':{'chip':'ESP32-P4','revision':103,'identity':'PRIVATE-FIXTURE-MAC','path':str(root)}}))
    browser=p.chromium.launch();page=browser.new_page();errors=[];requests=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    review_candidate=False
    approved_candidate=False
    app=bytes(image()); app_hash=hashlib.sha256(app).hexdigest()
    key=Ed25519PrivateKey.generate()
    def approved_release(previous=False):
        policy=json.loads((ROOT/'tests/fixtures/initial-release-v2.json').read_text())
        policy.update(sequence=7 if previous else 8,firmware_version='fixture-old' if previous else 'fixture-new',commissioning='usb-assisted-v1',usb_review='Fixture USB commissioning')
        policy['app'].update(size=len(app),sha256=app_hash)
        policy['bootloader_sha256']=hashlib.sha256(data[0x2000:0x8000]).hexdigest()
        policy['table_sha256']=hashlib.sha256(data[0x8000:0x9000]).hexdigest()
        payload=json.dumps(policy,sort_keys=True,separators=(',',':')).encode()
        return {'status':'reviewed-development-release','publisher_key':key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex(),
            'envelope':{'payload':base64.b64encode(payload).decode(),'signature':base64.b64encode(key.sign(payload)).decode()},
            'release_id':hashlib.sha256(payload).hexdigest(),'minimum_sequence':1}
    def route(r):
        req=r.request;requests.append((req.method,req.url))
        path=urlparse(req.url).path
        if path=='/devices/add/':r.fulfill(status=200,content_type='text/html',body=html)
        elif path=='/devices/firmware/release/':r.fulfill(status=200,content_type='application/json',body=json.dumps(approved_release(previous=urlparse(req.url).query=='recovery=1') if approved_candidate else {'status':'development-review','installable':False,'profile':'waveshare-7b-stock-v1','app':{'offset':0xe00000,'size':len(app),'sha256':app_hash}} if review_candidate else {'status':'no-reviewed-release','installable':False}))
        elif path=='/devices/firmware/artifacts/'+app_hash+'.bin':r.fulfill(status=200,content_type='application/octet-stream',body=app)
        elif path.startswith('/static/'):
            file=finders.find(path[len('/static/'):])
            if file:r.fulfill(status=200,content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream',body=Path(file).read_bytes())
            else:r.fulfill(status=404,body='')
        else:r.fulfill(status=404,body='')
    page.route('https://ampve.test/**',route)
    page.goto('https://ampve.test/devices/add/')
    assert page.locator('#backup-step').is_hidden()
    assert page.locator('#device-confirmation').is_hidden()
    assert page.locator('#wifi-step').is_hidden()
    assert page.locator('#pairing-step').is_hidden()
    assert 'bootloader' not in page.locator('body').inner_text().lower()
    page.locator('#resume-backups').click()
    page.locator('#board-confirm').check()
    page.locator('#confirm-device').click()
    page.locator('#use-existing').click()
    page.locator('#import-backups').set_input_files([str(root/name) for name in ['backup-a.bin','backup-b.bin','audit-private.json']])
    page.wait_for_function('document.querySelector("#backup-result").textContent.includes("saved copies match") && !document.querySelector("#prepare-install").disabled',timeout=30000)
    page.locator('#technical-review summary').click()
    operation_status=page.locator('#setup-status').inner_text()
    with page.expect_download() as download_event:
        page.locator('#export-review').click()
    assert page.locator('#setup-status').inner_text()==operation_status
    exported=Path(download_event.value.path()).read_text()
    review=json.loads(exported)
    assert review['kind']=='ampve-browser-review-summary' and review['installable'] is False
    assert review['evidence']['source']=='imported-capture-record'
    assert review['evidence']['current_physical_state_verified'] is False
    assert review['table_sha256']==hashlib.sha256(data[0x8000:0x9000]).hexdigest()
    assert review['images'][0]['region_sha256']==hashlib.sha256(data[0x2000:0x8000]).hexdigest()
    assert 'PRIVATE-FIXTURE-MAC' not in exported and str(root) not in exported

    assert any('/devices/firmware/release/' in url for _,url in requests)
    page.wait_for_function('document.querySelector("#release-status").textContent.includes("No approved installation")')
    assert page.locator('#install-ampve').is_disabled()
    assert page.locator('#plan-panel').is_hidden()
    review_candidate=True
    page.locator('#board-confirm').check()
    page.evaluate("""() => {
      window.fixtureRecoveryFiles={};
      const directory={getDirectoryHandle:async()=>directory,getFileHandle:async name=>({
        createWritable:async()=>({write:async data=>{window.fixtureRecoveryFiles[name]=new Blob([data]);},close:async()=>{},abort:async()=>{}}),
        getFile:async()=>window.fixtureRecoveryFiles[name]
      })};
      window.showDirectoryPicker=async()=>directory;
    }""")
    page.locator('#import-backups').set_input_files([str(root/name) for name in ['backup-b.bin','backup-a.bin','audit-private.json']])
    page.wait_for_function('document.querySelector("#setup-status").textContent.includes("Candidate compared")')
    assert page.locator('#plan-panel').is_visible()
    assert page.locator('#approve-plan').is_disabled()
    page.locator('#save-recovery').click()
    page.wait_for_function('document.querySelector("#setup-status").textContent.includes("Recovery files saved")')
    saved=page.evaluate('async()=>JSON.parse(await window.fixtureRecoveryFiles["recovery-plan-private.json"].text())')
    assert saved['installable'] is False
    assert [r['offset'] for r in saved['writes']]==[0xe00000,0x10d000]
    assert page.evaluate('window.fixtureRecoveryFiles["restore-otadata.bin"].size')==8192
    with page.expect_download() as event:
        page.locator('#export-plan-review').click()
    assert page.locator('#export-plan-review').get_attribute('href').startswith('blob:')
    assert event.value.suggested_filename=='ampve-plan-review-summary.json'
    exported_plan=Path(event.value.path()).read_text(); plan_review=json.loads(exported_plan)
    with page.expect_download() as repeated:
        page.locator('#export-plan-review').click()
    assert Path(repeated.value.path()).read_text()==exported_plan
    assert plan_review['kind']=='ampve-browser-plan-review' and plan_review['installable'] is False
    assert plan_review['candidate_sha256']==app_hash and plan_review['backup_sha256']==digest
    assert plan_review['current_selection'] is None and plan_review['recovery_files_saved'] is True
    assert plan_review['proposed_regions']==[{'offset':r['offset'],'size':r['size'],'sha256':r['sha256']} for r in saved['writes']]
    assert 'PRIVATE-FIXTURE-MAC' not in exported_plan and str(root) not in exported_plan
    page.locator('#separate-copy').check();page.locator('#rom-recovery').check()
    assert page.locator('#install-ampve').is_disabled()
    # Recovery must be reachable after reloading/importing original files, without a live ROM reader.
    page.evaluate("""() => {Object.defineProperty(navigator,'serial',{configurable:true,value:{
      requestPort:async()=>{window.recoveryPortRequests=(window.recoveryPortRequests||0)+1;throw new DOMException('Fixture cancellation','AbortError');},addEventListener(){}}});}""")
    approved_candidate=True
    page.locator('#recover-device').click()
    page.locator('#board-confirm').check();page.locator('#confirm-device').click()
    assert page.locator('#existing-backups').is_visible()
    page.locator('#import-backups').set_input_files([])
    page.wait_for_function('!document.querySelector("#import-backups").disabled')
    page.locator('#import-backups').set_input_files([str(root/name) for name in ['backup-a.bin','backup-b.bin','audit-private.json']])
    page.wait_for_function('document.querySelector("#installation-method").textContent.includes("fixture-new")')
    assert any(url.endswith('/devices/firmware/release/?recovery=1') for _,url in requests)
    assert any(url.endswith('/devices/firmware/artifacts/'+app_hash+'.bin?recovery=1') for _,url in requests)
    assert page.locator('#restore-panel').is_visible()
    assert page.locator('#restore-original').is_enabled()
    assert page.locator('#install-ampve').is_disabled()
    assert page.locator('#wifi-step').is_visible()
    page.locator('#save-recovery').click()
    page.wait_for_function('document.querySelector("#setup-status").textContent.includes("Recovery files saved")')
    for checkbox in ['separate-copy','rom-recovery','approve-plan']:page.locator('#'+checkbox).check()
    assert page.locator('#install-ampve').is_enabled()
    page.locator('#install-ampve').click()
    page.wait_for_function('window.recoveryPortRequests===1 && !document.querySelector("#restore-original").disabled')
    page.once('dialog',lambda dialog:dialog.accept())
    page.locator('#restore-original').click()
    page.wait_for_function('window.recoveryPortRequests===2 && !document.querySelector("#restore-original").disabled')
    assert page.locator('#setup-status').inner_text().startswith('Stopped.')
    assert page.locator('#restore-panel').is_visible()
    page.evaluate(r"""() => {
      const packet=(type,data)=>{const p=[73,77,80,82,79,86,1,type,data.length,...data];p.push(p.reduce((a,b)=>a+b,0)&255);return new Uint8Array([10,...p,10]);};
      const rpc=(command,strings)=>{const data=strings.flatMap(s=>{const b=[...new TextEncoder().encode(s)];return [b.length,...b];});return packet(4,[command,data.length,...data]);};
      const port={getInfo:()=>({usbVendorId:0x1a86,usbProductId:0x55d3}),async open(){
        this.readable=new ReadableStream({start:c=>this.input=c});
        this.writable=new WritableStream({write:bytes=>{
          if(bytes[9]===2)this.input.enqueue(packet(1,[2]));
          if(bytes[9]===3)this.input.enqueue(rpc(3,['AMPVE','fixture','waveshare-p4-7b','Fixture']));
          if(bytes[9]===1){window.fixtureCredentialWrites=(window.fixtureCredentialWrites||0)+1;setTimeout(()=>{this.input.enqueue(packet(1,[4]));this.input.enqueue(rpc(1,['https://untrusted.invalid/']));},300);}
        }});
      },async close(){if(this.readable.locked||this.writable.locked)throw new Error('Leaked reader');window.fixtureClosed=true;}};
      Object.defineProperty(navigator,'serial',{configurable:true,value:{requestPort:async()=>port,addEventListener(){}}});
    }""")
    # The existing page initially had Web Serial disabled in headless Chromium.
    page.locator('#already-installed').click()
    page.locator('#connect-wifi').evaluate('(button)=>button.disabled=false')
    page.locator('#connect-wifi').click()
    page.wait_for_function('!document.querySelector("#send-wifi").disabled')
    page.locator('#wifi-ssid').fill('Fixture')
    page.locator('#wifi-password').fill('fixture-password')
    page.locator('#send-wifi').click()
    assert page.locator('#wifi-password').input_value()==''
    assert page.locator('#inspect-chip').is_disabled()
    page.wait_for_function('document.querySelector("#wifi-status").textContent.includes("reports a Wi-Fi connection")')
    assert page.evaluate('window.fixtureCredentialWrites')==1
    assert page.url=='https://ampve.test/devices/add/'
    page.locator('#close-wifi').click()
    page.wait_for_function('window.fixtureClosed===true')
    page.evaluate(r"""async()=>{
      const port=await navigator.serial.requestPort();
      port.getInfo=()=>({usbVendorId:0x1a86,usbProductId:0x55d3});port.setSignals=async()=>{};
      port.open=async()=>{
        port.readable=new ReadableStream({start:c=>port.input=c});let sent=false;
        port.writable=new WritableStream({write:()=>{if(!sent){sent=true;port.input.enqueue(new TextEncoder().encode('assert failed: fixture_init /private/fixture.c:42 (private-expression)\nabort() was called at PC 0x480019e9 on core 0\nELF file SHA256: 6ea09dd6d\n'));}}});
      };
    }""")
    page.locator('#check-startup').click()
    page.wait_for_function('!document.querySelector("#export-install-result").hidden && !document.querySelector("#import-backups").disabled')
    assert page.locator('#wifi-step').is_visible()
    assert page.locator('#check-startup').is_enabled()
    assert page.locator('#connect-wifi').is_disabled()
    assert page.locator('#install-ampve').is_disabled()
    assert 'different AMPVE build' in page.locator('#setup-status').inner_text()
    failure_status=page.locator('#setup-status').inner_text()
    with page.expect_download() as result_download:page.locator('#export-install-result').click()
    failure=json.loads(Path(result_download.value.path()).read_text())
    assert failure['kind']=='ampve-usb-startup-failure' and failure['capture_stop']=='panic_captured'
    assert failure['build_identity']=='different_known_build'
    assert failure['observed_app_sha256']=='9431969a70d060db94f92a11873ce5200d597a6df199ceeed90c80de2deae33e'
    assert failure['assertion_locations']==[{'function':'fixture_init','file':'fixture.c','line':42}]
    assert 'private' not in json.dumps(failure)
    page.locator('#check-startup').click()
    page.wait_for_function('!document.querySelector("#check-startup").disabled')
    assert page.locator('#wifi-step').is_visible()
    assert page.locator('#setup-status').inner_text()==failure_status
    assert not any(method!='GET' for method,_ in requests),requests
    Path('.browser-tests').mkdir(exist_ok=True)
    for width in [390,768,1440]:
        page.set_viewport_size({'width':width,'height':950})
        page.wait_for_timeout(400)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        page.screenshot(path=f'.browser-tests/stock-onboarding-{width}.png',full_page=True)
    assert not errors,errors
    browser.close()
print('Rendered browser fixtures passed: local backup import/integrity, sanitized backup/plan downloads, candidate comparison and saved recovery, signed latest-version reinstall preparation without a live reader, enabled install after consent and cancelled-port retry, unsigned write gate, simulated USB Wi-Fi/password clearing, visible panic-result download without replacing the error, no uploads and three viewport widths. No physical hardware tested.')
