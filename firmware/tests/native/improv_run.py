"""Exercise the actual Improv core with the pinned official SDK, without UART/board access."""
from pathlib import Path
import argparse
import json
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser();parser.add_argument('--sdk',type=Path,required=True);args=parser.parse_args()
pin=json.loads((ROOT/'firmware/xiaozhi/improv.json').read_text())
assert subprocess.check_output(['git','-C',str(args.sdk),'rev-parse','HEAD']).decode().strip()==pin['commit']
with tempfile.TemporaryDirectory(prefix='ampve-improv-') as directory:
 binary=Path(directory)/'test'
 subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Wno-sign-compare','-O1','-g','-fsanitize=address,undefined',
  '-I'+str(args.sdk/'src'),'-I'+str(ROOT/'firmware/xiaozhi/overlay/main/ampve'),str(args.sdk/'src/improv.cpp'),
  str(ROOT/'firmware/xiaozhi/overlay/main/ampve/improv_service.cc'),str(ROOT/'firmware/tests/native/improv_harness.cc'),'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True)
