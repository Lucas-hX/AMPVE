"""Compile transformed upstream codec with injected driver faults; no board access."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'firmware/tools'))
from audio_guard import transform,SOURCE,HEADER
import json
pin=json.loads((ROOT/'firmware/xiaozhi/upstream.json').read_text())['commit']
parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
originals=[subprocess.check_output(['git','-C',str(args.work),'show',pin+':'+p]).decode() for p in [SOURCE,HEADER]]
source,header=transform(*originals)
with tempfile.TemporaryDirectory(prefix='ampve-audio-') as directory:
    tmp=Path(directory)
    (tmp/'box_audio_codec.cc').write_text(source);(tmp/'box_audio_codec.h').write_text(header)
    for name in ['esp_log.h','driver/i2c_master.h','driver/i2s_tdm.h','esp_codec_dev.h','esp_codec_dev_defaults.h','ampve/runtime.h']:
        p=tmp/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "fake_esp.h"\n')
    subprocess.run(['g++','-std=c++20','-Wall','-Werror','-O1','-g','-fsanitize=address,undefined','-I'+str(tmp),
        '-I'+str(ROOT/'firmware/tests/native/audio_stubs'),str(tmp/'box_audio_codec.cc'),
        str(ROOT/'firmware/tests/native/audio_harness.cc'),'-o',str(tmp/'test')],check=True)
    subprocess.run([str(tmp/'test')],check=True)
