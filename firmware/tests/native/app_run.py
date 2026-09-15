"""ASan/UBSan checks for actual signed package bytes and RAM-only rollback."""
import base64
import copy
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'apps/platform'))
from workspace.app_package_contract import validate  # noqa: E402
from workspace.hardware_profiles import CONTRACT  # noqa: E402
from workspace.release_contract import canonical  # noqa: E402

work=Path(sys.argv[1]);host=Path(sys.argv[2])
cjson=work/'managed_components/espressif__cjson/cJSON'
sodium=work/'managed_components/espressif__libsodium/libsodium/src/libsodium/include'
key=Ed25519PrivateKey.generate()
policy={'schema':1,'api_version':1,'key_id':'fixture-key','name':'timer-fixture',
    'version':'1.0.0','kind':'timer','profile_id':CONTRACT['profile_id'],
    'profile_version':1,'layout_id':CONTRACT['layout_id'],'chip_revision':103,
    'flash_bytes':33554432,'minimum_psram_bytes':33554432,
    'expires_at':'2030-01-01T00:00:00Z',
    'ui':{'title':'Fixture timer','body':'Local timer demonstration'},
    'workflow':{'action':'local_timer','duration_s':120,'start_muted':True}}
validate(policy)
def signed(p):
    payload=canonical(p)
    return {'payload':base64.b64encode(payload).decode(),
            'signature':base64.b64encode(key.sign(payload)).decode()},hashlib.sha256(payload).hexdigest()
context={'profile_id':CONTRACT['profile_id'],'layout_id':CONTRACT['layout_id'],
    'profile_version':1,'chip_revision':103,'flash_bytes':33554432,
    'now_utc':1789257600,'key_id':'fixture-key','authorized':1,'revoked':0,
    'public_key':key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex()}
with tempfile.TemporaryDirectory(prefix='ampve-app-native-') as folder:
    tmp=Path(folder)
    includes=['-I'+str(cjson),'-I'+str(sodium),'-I'+str(sodium/'sodium'),
              '-I'+str(host/'src/libsodium/include'),
              '-I'+str(ROOT/'firmware/xiaozhi/overlay/main/ampve')]
    subprocess.run(['cc','-c','-O1','-g','-fsanitize=address,undefined',
                    str(cjson/'cJSON.c'),'-o',str(tmp/'cjson.o')],check=True)
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-O1','-g',
        '-fsanitize=address,undefined',*includes,
        str(ROOT/'firmware/xiaozhi/overlay/main/ampve/app_package.cc'),
        str(ROOT/'firmware/xiaozhi/overlay/main/ampve/app_runtime.cc'),
        str(ROOT/'firmware/tests/native/app_harness.cc'),str(tmp/'cjson.o'),
        str(host/'src/libsodium/.libs/libsodium.a'),'-pthread','-o',str(tmp/'app')],check=True)
    (tmp/'context.json').write_bytes(canonical(context))
    valid,identity=signed(policy)
    cases=[('valid',valid,identity,'accepted'),
           ('interrupted',canonical(valid)[:-1],identity,'refused'),
           ('wrong-hash',valid,'0'*64,'refused'),
           ('oversized',' '*2049,identity,'refused'),
           ('bad-signature',{**valid,'signature':base64.b64encode(b'!'*64).decode()},identity,'refused')]
    status=copy.deepcopy(policy)
    status['kind']='status';status['name']='status-fixture'
    status['workflow']={'action':'show_status','duration_s':0,'start_muted':True}
    companion=copy.deepcopy(policy)
    companion['kind']='companion';companion['name']='companion-fixture'
    companion['workflow']={'action':'native_companion','duration_s':0,'start_muted':True}
    for name,policy_variant in [('status',status),('companion-muted',companion)]:
        validate(policy_variant)
        signed_variant,variant_id=signed(policy_variant)
        cases.append((name,signed_variant,variant_id,'accepted'))
    for kind,change in [('hardware',{'chip_revision':102}),
                        ('api',{'api_version':2}),
                        ('native',{'workflow':{'action':'execute_native','duration_s':120,'start_muted':True}}),
                        ('expired',{'expires_at':'2020-01-01T00:00:00Z'})]:
        modified=copy.deepcopy(policy);modified.update(change)
        envelope,new_id=signed(modified);cases.append((kind,envelope,new_id,'refused'))
    for name,envelope,expected,outcome in cases:
        path=tmp/(name+'.json')
        path.write_bytes(canonical(envelope) if isinstance(envelope,dict) else envelope.encode() if isinstance(envelope,str) else envelope)
        result=subprocess.check_output([str(tmp/'app'),str(path),str(tmp/'context.json'),expected,'verify'],text=True).strip()
        if result!=outcome:raise AssertionError((name,result,outcome))
    path=tmp/'valid.json'
    subprocess.run([str(tmp/'app'),str(path),str(tmp/'context.json'),identity,'runtime'],check=True)
    print('12 native app verifier/transition scenarios passed')
