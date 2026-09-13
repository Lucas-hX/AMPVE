#include "improv_platform.h"
#include "improv_service.h"
#include "runtime.h"
#include "wifi_manager.h"
#include "ssid_manager.h"
#include "driver/uart.h"
#include "driver/uart_vfs.h"
#include "esp_app_desc.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <atomic>
#include <cstdio>
#include <cstdarg>

namespace {
std::atomic<int64_t> authorization{0};
std::atomic<bool> started{false};
int serial_log(const char* format, va_list args) {
 // SSIDs in upstream logs are untrusted bytes. Escape control characters so
 // a diagnostic cannot inject the binary Improv version/type header.
 char message[512];
 int length=vsnprintf(message,sizeof(message),format,args);
 if(length<0)return length;
 flockfile(stdout);
 for(size_t i=0;i<sizeof(message)-1 && message[i];++i){
  auto byte=static_cast<unsigned char>(message[i]);
  if((byte<32 && byte!='\n' && byte!='\r' && byte!='\t') || byte==127){
   char escaped[5];snprintf(escaped,sizeof(escaped),"\\x%02x",byte);fwrite(escaped,1,4,stdout);
  }else fwrite(&message[i],1,1,stdout);
 }
 funlockfile(stdout);
 return length;
}
class Port final:public ampve::ImprovPort {
public:
 int64_t now() override{return esp_timer_get_time();}
 int64_t authorized_until() override{
  if(!ampve_wifi_initialized || !SsidManager::GetInstance().IsStorageReady() || !WifiManager::GetInstance().IsConfigMode())return 0;
  return authorization.load();
 }
 bool connected(const std::string& ssid) override{
  auto& wifi=WifiManager::GetInstance();return ampve_wifi_initialized && wifi.IsConnected() && (ssid.empty() || wifi.GetSsid()==ssid);
 }
 int configure(const std::string& ssid,const std::string& password,int64_t until) override{
  if(authorized_until()!=until || now()>=until)return -2;
  return WifiManager::GetInstance().ConfigureNetwork(ssid,password,until);
 }
 void handoff() override{auto& wifi=WifiManager::GetInstance();if(wifi.IsConfigMode())wifi.StartStation();}
 std::string version() override{return esp_app_get_description()->version;}
 void send(const uint8_t* bytes,size_t size) override{
  // Share stdout's lock with normal logs, but bypass text newline translation.
  flockfile(stdout);uart_write_bytes(UART_NUM_0,"\n",1);uart_write_bytes(UART_NUM_0,bytes,size);uart_write_bytes(UART_NUM_0,"\n",1);funlockfile(stdout);
 }
};
void worker(void*){
 Port port;ampve::ImprovService service(port);uint8_t bytes[64]={};
 while(true){
  int count=uart_read_bytes(UART_NUM_0,bytes,sizeof(bytes),pdMS_TO_TICKS(100));
  for(int i=0;i<count;++i){service.feed(bytes[i]);bytes[i]=0;}
  service.tick();
 }
}
}
void ampve_improv_authorize(){
 if(started && ampve_wifi_initialized && WifiManager::GetInstance().IsConfigMode()){ authorization=esp_timer_get_time()+300000000; WifiManager::GetInstance().RenewProvisioning(authorization.load()); }
}
bool ampve_improv_start(){
 if(started)return true;
 // Own one receive path. A pre-existing UART consumer is not silently displaced.
 if(uart_is_driver_installed(UART_NUM_0))return false;
 uart_config_t config={};config.baud_rate=115200;config.data_bits=UART_DATA_8_BITS;
 config.parity=UART_PARITY_DISABLE;config.stop_bits=UART_STOP_BITS_1;
 config.flow_ctrl=UART_HW_FLOWCTRL_DISABLE;config.source_clk=UART_SCLK_DEFAULT;
 flockfile(stdout);
 auto result=uart_param_config(UART_NUM_0,&config);
 if(result==ESP_OK)result=uart_driver_install(UART_NUM_0,512,0,0,nullptr,0);
 if(result==ESP_OK)uart_vfs_dev_use_driver(UART_NUM_0);
 funlockfile(stdout);
 if(result!=ESP_OK)return false;
 esp_log_set_vprintf(serial_log);
 if(xTaskCreate(worker,"ampve_improv",8192,nullptr,2,nullptr)!=pdPASS){
  flockfile(stdout);uart_vfs_dev_use_nonblocking(UART_NUM_0);uart_driver_delete(UART_NUM_0);funlockfile(stdout);
  return false;
 }
 started=true;return true;
}
