"""Fault-inject the actual transformed P4 board/MIPI startup methods with fake driver APIs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'firmware/tools'))
from board_guard import BOARD,DISPLAY,transform,transform_display
pin=json.loads((ROOT/'firmware/xiaozhi/upstream.json').read_text())['commit']
parser=argparse.ArgumentParser();parser.add_argument('--work',required=True,type=Path);args=parser.parse_args()
def original(path):return subprocess.check_output(['git','-C',str(args.work),'show',pin+':'+path]).decode()
def method(source,signature):
    a=source.index(signature);start=source.index('{',a);depth=1;b=start+1
    while depth:
        if source[b]=='{':depth+=1
        if source[b]=='}':depth-=1
        b+=1
    return source[a:b]
board=transform(original(BOARD));display=transform_display(original(DISPLAY))
methods='\n'.join(method(board,s) for s in ['bool InitializeCodecI2c()', 'static esp_err_t bsp_enable_dsi_phy_power(void)', 'bool InitializeLCD()'])
touch=method(board,'void InitializeTouch()')
constructor=method(board,'WaveshareEsp32p4() :');body=constructor[constructor.index('{')+1:-1]
source='''#include "display_stubs.h"
#include <iostream>
'''+method(display,'MipiLcdDisplay::MipiLcdDisplay(')+'''
class TouchHarness {
public:
 void* i2c_bus_=reinterpret_cast<void*>(uintptr_t(1));
 int i2c_device_probe(int address){return address==ESP_LCD_TOUCH_IO_I2C_GT911_ADDRESS?ESP_OK:ESP_FAIL;}
'''+touch+'''
};
class BoardHarness {
public:
 void* i2c_bus_=nullptr;LcdDisplay* display_=nullptr;
 struct Light {void RestoreBrightness(){++later_calls;}} light;
 void InitializeTouch(){++later_calls;ampve_touch_ready=true;}
 void InitializeButtons(){++later_calls;}
 Light* GetBacklight(){return &light;}
 int i2c_device_probe(int){assert(i2c_bus_);return 0;}
 BoardHarness(){'''+body+'''}
 ~BoardHarness(){delete display_;}
'''+methods+'''
};
int main(){
 int cases=0;
 for(int failure=0;failure<=10;++failure){
  ampve_touch_ready=false;ampve_codec_present=false;calls=later_calls=0;fail_at=failure;null_at=0;default_display=nullptr;
  {BoardHarness board; if(!failure){assert(calls==10 && later_calls==3);}else{assert(calls==failure && later_calls==0 && !ampve_touch_ready && !ampve_codec_present);}}
  ++cases;
 }
 for(int missing: {1,2,3,4,5,10}){
  ampve_touch_ready=false;ampve_codec_present=false;calls=later_calls=0;fail_at=0;null_at=missing;default_display=nullptr;
  {BoardHarness board;assert(calls==missing && later_calls==0 && !ampve_touch_ready && !ampve_codec_present);}
  ++cases;
 }
 ampve_touch_ready=false;ampve_codec_present=false;calls=later_calls=0;fail_at=null_at=0;default_display=nullptr;missing_default=true;
 {BoardHarness board;assert(calls==10 && later_calls==0);}++cases;
 ampve_touch_ready=false;touch_swap_xy=touch_mirror_x=touch_mirror_y=-1;missing_default=false;default_display=reinterpret_cast<void*>(uintptr_t(5));
 {TouchHarness touch;touch.InitializeTouch();}
 assert(ampve_touch_ready && touch_swap_xy==0 && touch_mirror_x==1 && touch_mirror_y==1);++cases;
 std::cout << cases << " display/touch startup scenarios passed; 7B coordinates match the board BSP\\n";
}
'''
with tempfile.TemporaryDirectory(prefix='ampve-display-') as directory:
    tmp=Path(directory);(tmp/'test.cc').write_text(source)
    subprocess.run(['g++','-std=c++20','-Wall','-Werror','-O1','-g','-fsanitize=address,undefined',
        '-I'+str(ROOT/'firmware/tests/native'),str(tmp/'test.cc'),'-o',str(tmp/'test')],check=True)
    subprocess.run([str(tmp/'test')],check=True)
