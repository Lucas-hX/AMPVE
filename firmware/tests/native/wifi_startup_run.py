"""Run the actual patched Wi-Fi initializer with simulated ESP/NVS failures."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'firmware/tools'))
from wifi_guard import transform_manager
parser=argparse.ArgumentParser();parser.add_argument('--work',required=True,type=Path);args=parser.parse_args()
source=transform_manager((args.work/'managed_components/78__esp-wifi-connect/wifi_manager.cc').read_text())
a=source.index('bool WifiManager::Initialize(');b=source.index('\nbool WifiManager::IsInitialized',a)
source='''#include <cassert>
#include <memory>
#include <mutex>
#include <iostream>
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_ERROR_CHECK(call) assert((call)==0)
#define WIFI_INIT_CONFIG_DEFAULT() {}
using esp_err_t=int;
constexpr int ESP_OK=0,ESP_ERR_INVALID_STATE=1,ESP_ERR_NVS_NO_FREE_PAGES=2,ESP_ERR_NVS_NEW_VERSION_FOUND=3;
int results[4]={},calls=0,erases=0;
int nvs_flash_init(){assert(calls==0);return results[calls++];}
int nvs_flash_erase(){++erases;return 0;}
int esp_netif_init(){assert(calls==1);return results[calls++];}
int esp_event_loop_create_default(){assert(calls==2);return results[calls++];}
struct wifi_init_config_t {bool nvs_enable=true;};
int esp_wifi_init(wifi_init_config_t* cfg){assert(calls==3 && !cfg->nvs_enable);return results[calls++];}
struct WifiManagerConfig {};
struct WifiStation {};struct WifiConfigurationAp {};
class WifiManager {
public:
 bool Initialize(const WifiManagerConfig&);
 std::mutex mutex_;bool initialized_=false;WifiManagerConfig config_;
 std::unique_ptr<WifiStation> station_;
 std::unique_ptr<WifiConfigurationAp> config_ap_;
};
'''+source[a:b]+'''
int main(){
 int cases=0;
 for(int stage=0;stage<4;++stage){
  for(int error: {-1,ESP_ERR_NVS_NO_FREE_PAGES,ESP_ERR_NVS_NEW_VERSION_FOUND}){
   for(auto& value:results)value=0;
   results[stage]=error;calls=erases=0;WifiManager manager;
   assert(!manager.Initialize({}) && calls==stage+1 && erases==0);
   assert(!manager.initialized_ && !manager.station_ && !manager.config_ap_);++cases;
  }
 }
 for(bool existing: {false,true}){
  for(auto& value:results)value=0;
  if(existing)results[1]=results[2]=ESP_ERR_INVALID_STATE;
  calls=erases=0;WifiManager manager;
  assert(manager.Initialize({}) && calls==4 && erases==0 && manager.station_ && manager.config_ap_);
  assert(manager.Initialize({}) && calls==4 && erases==0);++cases;
 }
 std::cout << cases << " Wi-Fi startup scenarios passed; NVS never erased\\n";
}
'''
with tempfile.TemporaryDirectory(prefix='ampve-wifi-startup-') as directory:
    tmp=Path(directory);(tmp/'test.cc').write_text(source)
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined',str(tmp/'test.cc'),'-o',str(tmp/'test')],check=True)
    subprocess.run([str(tmp/'test')],check=True)
