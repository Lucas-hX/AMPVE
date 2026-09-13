"""Fault-inject the patched portal connection method with simulated driver/events."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'firmware/tools'))
from credential_guard import connection
parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
s=connection((args.work/'managed_components/78__esp-wifi-connect/wifi_configuration_ap.cc').read_text())
a=s.index('bool WifiConfigurationAp::ConnectToWifi(');b=s.index('\nvoid WifiConfigurationAp::Save(',a)
source='''#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <iostream>
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define pdMS_TO_TICKS(x) (x)
constexpr int ESP_OK=0,WIFI_IF_STA=0,WIFI_ALL_CHANNEL_SCAN=0,WIFI_CONNECTED_BIT=1,WIFI_FAIL_BIT=2,pdTRUE=1,pdFALSE=0;
using EventBits_t=int;
int config_result=0,connect_result=0,configs=0,connects=0,disconnects=0,waits=0,delays=0;
int events[2]={WIFI_FAIL_BIT,WIFI_FAIL_BIT};
struct wifi_config_t {struct {char ssid[32];char password[64];int scan_method,failure_retry_cnt;}sta;};
struct wifi_ap_record_t {uint8_t primary;};
void xEventGroupClearBits(int,int){}
int esp_wifi_scan_stop(){return -1;}
int esp_wifi_set_config(int,const wifi_config_t*){++configs;return config_result;}
int esp_wifi_connect(){++connects;return connect_result;}
int esp_wifi_disconnect(){++disconnects;return 0;}
int esp_wifi_sta_get_ap_info(wifi_ap_record_t* record){record->primary=6;return 0;}
int xEventGroupWaitBits(int,int,int,int,int timeout){assert(timeout==10000);assert(waits<2);return events[waits++];}
void vTaskDelay(int delay){assert(delay==3000);delays+=delay;}
class WifiConfigurationAp {
public:
 bool is_connecting_=false;uint8_t last_connected_channel_=0;int event_group_=1;
 bool ConnectToWifi(const std::string&,const std::string&);
};
'''+s[a:b]+'''
int main(){
 int cases=0;
 for(int mode=0;mode<8;++mode){
  config_result=connect_result=configs=connects=disconnects=waits=delays=0;
  events[0]=events[1]=WIFI_FAIL_BIT;
  if(mode==0)config_result=-1;
  if(mode==1)connect_result=-1;
  if(mode==2)events[0]=events[1]=0;
  if(mode==3)events[1]=WIFI_CONNECTED_BIT;
  if(mode==4)events[0]=WIFI_CONNECTED_BIT;
  std::string ssid=mode==5?"":mode==6?std::string(33,'x'):"Fixture network";
  std::string password=mode==7?std::string(65,'x'):"fixture-password";
  WifiConfigurationAp ap;bool result=ap.ConnectToWifi(ssid,password);
  assert(result==(mode==3 || mode==4));assert(!ap.is_connecting_);
  assert(configs<=2 && connects<=2 && waits<=2 && delays<=3000);
  if(mode==0)assert(configs==1 && connects==0 && waits==0);
  if(mode>=5)assert(configs==0 && connects==0);
  if(mode==2)assert(disconnects==2);
  if(result)assert(ap.last_connected_channel_==6);
  ++cases;
 }
 std::cout<<cases<<" Wi-Fi connection scenarios passed without driver-error aborts\\n";
}
'''
with tempfile.TemporaryDirectory(prefix='ampve-connect-') as directory:
    tmp=Path(directory);(tmp/'test.cc').write_text(source)
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-variable','-O1','-g','-fsanitize=address,undefined',str(tmp/'test.cc'),'-o',str(tmp/'test')],check=True)
    subprocess.run([str(tmp/'test')],check=True)
