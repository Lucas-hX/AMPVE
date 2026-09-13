"""Integrate checked single-blob Wi-Fi storage into the pinned component."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[2]

def replace(source,old,new):
    if source.count(old)!=1:raise ValueError('Credential contract changed: '+old[:70])
    return source.replace(old,new)

def method(source,signature,body):
    a=source.index(signature);start=source.index('{',a);depth=1;b=start+1
    while depth:
        if source[b]=='{':depth+=1
        if source[b]=='}':depth-=1
        b+=1
    return source[:a]+body+source[b:]

def manager(source,header):
    header=replace(header,'#include <vector>','#include <vector>\n#include <mutex>')
    for name in ['AddSsid','UpdateSsidChannel','RemoveSsid','SetDefaultSsid','Clear']:
        header=replace(header,'    void '+name+'(', '    bool '+name+'(')
    header=replace(header,'    void SaveToNvs();','    bool SaveToNvs(const std::vector<SsidItem>& previous);\n    bool storage_ready_ = false;\n    mutable std::mutex mutex_;')
    header=replace(header,'    const std::vector<SsidItem>& GetSsidList() const { return ssid_list_; }',
        '    std::vector<SsidItem> GetSsidList() const { std::lock_guard<std::mutex> lock(mutex_); return ssid_list_; }\n    bool IsStorageReady() const { std::lock_guard<std::mutex> lock(mutex_); return storage_ready_; }')
    source=replace(source,'#include "ssid_manager.h"','#include "ssid_manager.h"\n#include "ampve_credentials.h"')
    a=source.index('static std::string MakeWifiKey(');b=source.index('SsidManager::SsidManager()',a);source=source[:a]+source[b:]
    source=method(source,'void SsidManager::LoadFromNvs()', '''void SsidManager::LoadFromNvs() {
    storage_ready_ = ampve_wifi::load(ssid_list_);
    if (!storage_ready_) ESP_LOGE(TAG, "Wi-Fi storage unavailable; data preserved");
}''')
    source=method(source,'void SsidManager::SaveToNvs()', '''bool SsidManager::SaveToNvs(const std::vector<SsidItem>& previous) {
    if (!storage_ready_ || !ampve_wifi::save(ssid_list_, previous)) {
        ssid_list_ = previous;
        storage_ready_ = false;
        ESP_LOGE(TAG, "Wi-Fi save failed or uncertain; restart before another change");
        return false;
    }
    return true;
}''')
    bodies={
        'Clear':'''bool SsidManager::Clear() {
    std::lock_guard<std::mutex> lock(mutex_);if (!storage_ready_) return false;
    auto previous=ssid_list_;ssid_list_.clear();return SaveToNvs(previous);
}''',
        'AddSsid':'''bool SsidManager::AddSsid(const std::string& ssid, const std::string& password, uint8_t channel) {
    std::lock_guard<std::mutex> lock(mutex_);if (!storage_ready_) return false;
    auto previous=ssid_list_;
    for (auto& item:ssid_list_) if (item.ssid==ssid) {
        item.password=password;if(channel)item.channel=channel;return SaveToNvs(previous);
    }
    if(ssid_list_.size()>=MAX_WIFI_SSID_COUNT)ssid_list_.pop_back();
    ssid_list_.insert(ssid_list_.begin(),{ssid,password,channel});return SaveToNvs(previous);
}''',
        'UpdateSsidChannel':'''bool SsidManager::UpdateSsidChannel(const std::string& ssid,uint8_t channel) {
    std::lock_guard<std::mutex> lock(mutex_);if (!storage_ready_) return false;
    if(!channel)return true;
    for(auto& item:ssid_list_)if(item.ssid==ssid){
        if(item.channel==channel)return true;
        auto previous=ssid_list_;item.channel=channel;return SaveToNvs(previous);
    }
    return false;
}''',
        'RemoveSsid':'''bool SsidManager::RemoveSsid(int index) {
    std::lock_guard<std::mutex> lock(mutex_);if (!storage_ready_ || index<0 || static_cast<size_t>(index)>=ssid_list_.size())return false;
    auto previous=ssid_list_;ssid_list_.erase(ssid_list_.begin()+index);return SaveToNvs(previous);
}''',
        'SetDefaultSsid':'''bool SsidManager::SetDefaultSsid(int index) {
    std::lock_guard<std::mutex> lock(mutex_);if (!storage_ready_ || index<0 || static_cast<size_t>(index)>=ssid_list_.size())return false;
    if(!index)return true;
    auto previous=ssid_list_;auto item=ssid_list_[index];
    ssid_list_.erase(ssid_list_.begin()+index);ssid_list_.insert(ssid_list_.begin(),item);return SaveToNvs(previous);
}'''}
    for name,body in bodies.items():source=method(source,'void SsidManager::'+name+'(',body)
    source=replace(source,'std::vector<uint8_t> SsidManager::GetSavedChannels() const {',
        'std::vector<uint8_t> SsidManager::GetSavedChannels() const {\n    std::lock_guard<std::mutex> lock(mutex_);')
    return source,header


def connection(source):
    return replace(source,'        ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));',
        '        if (esp_wifi_set_config(WIFI_IF_STA, &wifi_config) != ESP_OK) { is_connecting_ = false; ESP_LOGE(TAG, "Wi-Fi configuration rejected"); return false; }')


def prepare(work):
    target=work/'components/78__esp-wifi-connect'
    if not target.exists():return
    original=work/'managed_components/78__esp-wifi-connect'
    paths=['ssid_manager.cc','include/ssid_manager.h']
    originals=[(original/p).read_text() for p in paths]
    for path,old,new in zip(paths,originals,manager(*originals)):
        out=target/path
        if out.read_text() not in [old,new]:raise ValueError('Refusing unrelated credentials changes: '+path)
        if out.read_text()!=new:out.write_text(new)
    for path in (ROOT/'firmware/xiaozhi/wifi-overlay').iterdir():shutil.copyfile(path,target/path.name)
    cmake=target/'CMakeLists.txt';s=cmake.read_text()
    if '"ampve_credentials.cc"' not in s:
        s=s.replace('"ssid_manager.cc"','"ssid_manager.cc"\n            "ampve_credentials.cc"')
        s=s.replace('REQUIRES "esp_timer"','REQUIRES espressif__cjson "esp_timer"')
        cmake.write_text(s)
    header=target/'include/wifi_configuration_ap.h'
    if '    void Save(' in header.read_text():header.write_text(replace(header.read_text(),'    void Save(', '    bool Save('))
    ap=target/'wifi_configuration_ap.cc';s=ap.read_text()
    if 'void WifiConfigurationAp::Save(' in s:
        s=replace(s,'void WifiConfigurationAp::Save(', 'bool WifiConfigurationAp::Save(')
        s=replace(s,'    SsidManager::GetInstance().AddSsid(ssid, password, channel);', '    return SsidManager::GetInstance().AddSsid(ssid, password, channel);')
        s=replace(s,'            this_->Save(ssid_str, password_str);', '''            if (!this_->Save(ssid_str, password_str)) {
                cJSON_Delete(json);
                httpd_resp_send(req, "{\\"success\\":false,\\"error\\":\\"Could not confirm saved Wi-Fi settings. Restart before retrying.\\"}", HTTPD_RESP_USE_STRLEN);
                return ESP_OK;
            }''')
        for name in ['SetDefaultSsid','RemoveSsid']:
            s=replace(s,'                SsidManager::GetInstance().'+name+'(index);',
                '                if (!SsidManager::GetInstance().'+name+'(index)) return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Wi-Fi settings not saved; restart before retrying");')
        s=replace(s,'            ESP_LOGI(TAG, "SmartConfig SSID: %s, Password: %s", ssid, password);',
            '            // AMPVE: never log Wi-Fi credentials.')
        s=replace(s,'            self->Save(ssid, password);','            if (!self->Save(ssid, password)) return;')
        ap.write_text(s)
    s=ap.read_text()
    if 'ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config))' in s:ap.write_text(connection(s))
    html=target/'assets/wifi_configuration.html';s=html.read_text()
    for endpoint in ['delete','set_default']:
        old="fetch('/saved/"+endpoint+"?index=' + index)\n                .then(response => response.json())\n                .then(data => {\n                    loadSavedList();\n                });"
        if old in s:
            new="fetch('/saved/"+endpoint+"?index=' + index)\n                .then(response => { if (!response.ok) throw new Error('Wi-Fi settings were not saved. Restart before retrying.'); return response.json(); })\n                .then(() => loadSavedList())\n                .catch(error => showToast(error.message))\n                .finally(() => { item.disabled = false; });"
            s=replace(s,old,new)
    html.write_text(s)
