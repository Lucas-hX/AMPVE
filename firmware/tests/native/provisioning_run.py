"""Exercise actual prepared AP transaction/stop methods with a simulated radio."""
import argparse
from pathlib import Path
import subprocess
import tempfile
parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
s=(args.work/'components/78__esp-wifi-connect/wifi_configuration_ap.cc').read_text()
a=s.index('bool WifiConfigurationAp::Stop()');b=s.index('// AMPVE: one radio/storage transaction',a)
stop=s[a:b]
provision=s[s.index('int WifiConfigurationAp::Provision('):]
source=r'''
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstdint>
#include <iostream>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#define CONFIG_IDF_TARGET_ESP32P4 1
#define ESP_LOGI(...) ((void)0)
constexpr int WIFI_EVENT=1,ESP_EVENT_ANY_ID=2,IP_EVENT=3,IP_EVENT_STA_GOT_IP=4;
std::atomic<int64_t> clock_time{1};
int64_t esp_timer_get_time(){return clock_time.load();}
void esp_timer_stop(void*){}
void esp_timer_delete(void*){}
void httpd_stop(void*){}
void esp_event_handler_instance_unregister(int,int,void*){}
void esp_netif_destroy_default_wifi(void*){}
int stops=0;
void esp_wifi_stop(){++stops;}
struct Dns{void Stop(){}};
struct WifiConfigurationAp {
 std::mutex provisioning_mutex_, gate;
 std::condition_variable condition;
 bool provisioning_active_=true,block=false,entered=false,released=false,connect_ok=true,save_ok=true;
 std::atomic<int64_t> provisioning_deadline_{100};
 int connects=0,saves=0;int64_t after_connect=1;
 void *scan_timer_=nullptr,*server_=nullptr,*instance_any_id_=nullptr,*instance_got_ip_=nullptr,*ap_netif_=nullptr;
 std::unique_ptr<Dns> dns_server_;
 bool Stop();int Provision(const std::string&,const std::string&,int64_t);
 bool ConnectToWifi(const std::string&,const std::string&){
  ++connects;std::unique_lock<std::mutex> lock(gate);entered=true;condition.notify_all();
  if(block)condition.wait(lock,[this]{return released;});
  clock_time=after_connect;return connect_ok;
 }
 bool Save(const std::string&,const std::string&){++saves;return save_ok;}
};
'''+stop+provision+r'''
int main(){
 int cases=0;
 for(int mode=0;mode<8;++mode){
  clock_time=1;WifiConfigurationAp ap;
  if(mode==1)ap.provisioning_active_=false;
  if(mode==2)clock_time=100;
  if(mode==3)ap.connect_ok=false;
  if(mode==4)ap.after_connect=100;
  if(mode==5)ap.save_ok=false;
  if(mode==6)ap.after_connect=50;
  if(mode==7)ap.after_connect=100;
  int result=ap.Provision("Fixture","fixture-password",mode==6?50:mode==7?200:0);
  const int expected[]={1,-3,-2,0,-2,-1,-2,-2};assert(result==expected[mode]);
  assert(ap.saves==((mode==0 || mode==5)?1:0));++cases;
 }
 {clock_time=1;WifiConfigurationAp ap;ap.block=true;int result=0;
  std::thread worker([&]{result=ap.Provision("Fixture","fixture-password",100);});
  {std::unique_lock<std::mutex> lock(ap.gate);ap.condition.wait(lock,[&]{return ap.entered;});}
  assert(ap.Provision("Other","other-password",100)==-3);assert(!ap.Stop());assert(stops==0);
  {std::lock_guard<std::mutex> lock(ap.gate);ap.released=true;}ap.condition.notify_all();worker.join();
  assert(result==1 && ap.connects==1 && ap.saves==1);assert(ap.Stop());assert(stops==1);
  assert(ap.Provision("Other","other-password",100)==-3);++cases;
 }
 std::cout<<cases<<" provisioning lease/expiry scenarios passed with simulated radio/storage\n";
}
'''
with tempfile.TemporaryDirectory(prefix='ampve-provision-') as directory:
 p=Path(directory);(p/'test.cc').write_text(source)
 subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-pthread','-O1','-g','-fsanitize=address,undefined',str(p/'test.cc'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,timeout=15)
