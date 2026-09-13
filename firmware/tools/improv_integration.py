"""Traceable official SDK and coordinated portal/serial provisioning integration."""
import json
import shutil
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PIN=json.loads((ROOT/'firmware/xiaozhi/improv.json').read_text())

def replace(s,old,new):
    if s.count(old)!=1:raise ValueError('Improv integration contract changed: '+old[:70])
    return s.replace(old,new)

def manager(s):
    # Both paths must leave AP state unchanged if a provisioning transaction holds its lease.
    start=s.index('void WifiManager::StartStation()')
    tail=s[start:]
    if tail.count('config_ap_->Stop();')!=2:raise ValueError('Wi-Fi stop contract changed')
    s=s[:start]+tail.replace('config_ap_->Stop();','if (!config_ap_->Stop()) return;')
    s+='''
// AMPVE: the AP object lives for the manager lifetime; its own lease protects startup/stop.
int WifiManager::ConfigureNetwork(const std::string& ssid, const std::string& password, int64_t expires) {
    WifiConfigurationAp* target;
    { std::lock_guard<std::mutex> lock(mutex_);
      if (!initialized_ || !config_mode_active_ || !config_ap_) return -3;
      target=config_ap_.get(); }
    return target->Provision(ssid,password,expires);
}
void WifiManager::RenewProvisioning(int64_t until) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (initialized_ && config_mode_active_ && config_ap_) config_ap_->RenewProvisioning(until);
}
'''
    return s

def manager_header(s):
    return replace(s,'    bool IsInitialized() const;','    bool IsInitialized() const;\n    int ConfigureNetwork(const std::string& ssid, const std::string& password, int64_t expires);\n    void RenewProvisioning(int64_t until);')

def prepare(work):
    sdk=work.parent/'improv-sdk'
    if not sdk.exists():
        subprocess.run(['git','clone',PIN['repository'],str(sdk)],check=True)
        subprocess.run(['git','-C',str(sdk),'checkout','--detach',PIN['commit']],check=True)
    if subprocess.check_output(['git','-C',str(sdk),'rev-parse','HEAD']).decode().strip()!=PIN['commit']:
        raise ValueError('Unreviewed Improv SDK checkout')
    subprocess.run(['git','-C',str(sdk),'diff','--exit-code','HEAD','--','src','CMakeLists.txt','LICENSE'],check=True,stdout=subprocess.DEVNULL)
    destination=work/'components/ampve_improv_sdk'
    if destination.exists() and not (destination/'.ampve-source.json').exists():raise ValueError('Untracked Improv component')
    destination.mkdir(parents=True,exist_ok=True)
    for name in ['src/improv.h','src/improv.cpp','CMakeLists.txt','LICENSE']:
        out=destination/name;out.parent.mkdir(parents=True,exist_ok=True)
        if out.exists() and out.read_bytes()!=(sdk/name).read_bytes():raise ValueError('Modified Improv SDK artifact')
        if not out.exists():shutil.copyfile(sdk/name,out)
    (destination/'.ampve-source.json').write_text(json.dumps(PIN,sort_keys=True)+'\n')
    target=work/'components/78__esp-wifi-connect';original=work/'managed_components/78__esp-wifi-connect'
    if not target.exists():return
    h=target/'include/wifi_manager.h';old=(original/'include/wifi_manager.h').read_text();new=manager_header(old)
    if h.read_text() not in [old,new]:raise ValueError('Unrelated manager header changes')
    if h.read_text()!=new:h.write_text(new)
    h=target/'include/wifi_configuration_ap.h';s=h.read_text()
    if 'provisioning_mutex_' not in s:
        s=replace(s,'    void Stop();','    bool Stop();\n    int Provision(const std::string& ssid, const std::string& password, int64_t expires);')
        s=replace(s,'    std::mutex mutex_;','    std::mutex provisioning_mutex_;\n    bool provisioning_active_ = false;\n    std::mutex mutex_;')
        s=replace(s,'    bool is_connecting_ = false;','    std::atomic<bool> is_connecting_{false};')
        s='#include <atomic>\n'+s;h.write_text(s)
    s=h.read_text()
    if 'provisioning_deadline_' not in s:
        s=replace(s,'    bool provisioning_active_ = false;', '    bool provisioning_active_ = false;\n    std::atomic<int64_t> provisioning_deadline_{0};')
        s=replace(s,'    bool Stop();', '    bool Stop();\n    void RenewProvisioning(int64_t until) { provisioning_deadline_ = until; }')
        h.write_text(s)
    ap=target/'wifi_configuration_ap.cc';s=ap.read_text()
    if 'int WifiConfigurationAp::Provision(' not in s:
        s=replace(s,'void WifiConfigurationAp::Start()\n{','void WifiConfigurationAp::Start()\n{\n    std::lock_guard<std::mutex> lease(provisioning_mutex_);')
        s=replace(s,'    StartWebServer();','    StartWebServer();\n    provisioning_active_ = true;')
        s=replace(s,'void WifiConfigurationAp::Stop() {',
            'bool WifiConfigurationAp::Stop() {\n    std::unique_lock<std::mutex> lease(provisioning_mutex_, std::try_to_lock);\n    if (!lease.owns_lock()) return false;\n    provisioning_active_ = false;')
        s=replace(s,'    ESP_LOGI(TAG, "Wifi configuration AP stopped");','    ESP_LOGI(TAG, "Wifi configuration AP stopped");\n    return true;')
        s=replace(s,'            if (!this_->ConnectToWifi(ssid_str, password_str)) {','            int provisioning_result = this_->Provision(ssid_str, password_str, 0);\n            if (provisioning_result == 0) {')
        s=replace(s,'            if (!this_->Save(ssid_str, password_str)) {','            if (provisioning_result != 1) {')
        s+='''
// AMPVE: one radio/storage transaction across portal and serial; stop never invalidates it.
int WifiConfigurationAp::Provision(const std::string& ssid, const std::string& password, int64_t expires) {
    std::unique_lock<std::mutex> lease(provisioning_mutex_, std::try_to_lock);
    if (!lease.owns_lock() || !provisioning_active_) return -3;
    if (expires && esp_timer_get_time() >= expires) return -2;
    if (!ConnectToWifi(ssid,password)) return 0;
    if (expires && esp_timer_get_time() >= expires) return -2;
    return Save(ssid,password) ? 1 : -1;
}
''';ap.write_text(s)

    s=ap.read_text()
    if 'provisioning_deadline_ = esp_timer_get_time()' not in s:
        s=replace(s,'    provisioning_active_ = true;', '    provisioning_active_ = true;\n    provisioning_deadline_ = esp_timer_get_time() + 300000000;')
        s=replace(s,'    if (expires && esp_timer_get_time() >= expires) return -2;\n    if (!ConnectToWifi',
            '    auto local_deadline = provisioning_deadline_.load();\n    if (!expires || expires > local_deadline) expires = local_deadline;\n    if (esp_timer_get_time() >= expires) return -2;\n    if (!ConnectToWifi')
        ap.write_text(s)
