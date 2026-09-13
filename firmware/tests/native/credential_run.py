"""Compile actual Wi-Fi storage and patched SSID manager with simulated NVS."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'firmware/tools'))
from credential_guard import manager
parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
original=args.work/'managed_components/78__esp-wifi-connect'
source,header=manager((original/'ssid_manager.cc').read_text(),(original/'include/ssid_manager.h').read_text())
cjson=args.work/'managed_components/espressif__cjson/cJSON'
with tempfile.TemporaryDirectory(prefix='ampve-credentials-') as directory:
    tmp=Path(directory);(tmp/'ssid_manager.cc').write_text(source);(tmp/'ssid_manager.h').write_text(header)
    for p in (ROOT/'firmware/xiaozhi/wifi-overlay').iterdir():shutil.copyfile(p,tmp/p.name)
    subprocess.run(['cc','-O1','-g','-fsanitize=address,undefined','-c',str(cjson/'cJSON.c'),'-o',str(tmp/'json.o')],check=True)
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined','-pthread',
        '-I'+str(tmp),'-I'+str(cjson),'-I'+str(ROOT/'firmware/tests/native/credential_stubs'),
        str(tmp/'ampve_credentials.cc'),str(tmp/'ssid_manager.cc'),str(ROOT/'firmware/tests/native/credential_harness.cc'),str(tmp/'json.o'),'-o',str(tmp/'test')],check=True)
    cases=['normal','fresh','orphan','missing_password','wrong_type','long_legacy','open_read','legacy_read','malformed','oversized','trailing','nul_escape','blob_read','open_write','set_before','set_after','commit','concurrent','schema','fraction','duplicate','missing_previous','bounds']
    for case in cases:subprocess.run([str(tmp/'test'),case],check=True)
    print(f'{len(cases)} credential storage scenarios passed with simulated NVS; no hardware writes')
