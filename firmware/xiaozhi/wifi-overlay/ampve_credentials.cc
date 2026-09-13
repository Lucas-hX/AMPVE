#include "ampve_credentials.h"
#include "cJSON.h"
#include "nvs.h"
#include <cmath>
#include <cstring>
#include <memory>

namespace ampve_wifi {
namespace {
constexpr size_t kLimit=16384;
struct Store {
    nvs_handle_t handle=0;
    ~Store(){if(handle)nvs_close(handle);}
};
using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
bool valid(const SsidItem& item) {
    return !item.ssid.empty() && item.ssid.size()<=32 && item.password.size()<=64 &&
        item.ssid.find('\0')==std::string::npos && item.password.find('\0')==std::string::npos &&
        (item.channel<=14 || (item.channel>=36 && item.channel<=177));
}
bool valid(const std::vector<SsidItem>& entries) {
    if(entries.size()>10)return false;
    for(size_t i=0;i<entries.size();++i){
        if(!valid(entries[i]))return false;
        for(size_t j=0;j<i;++j)if(entries[i].ssid==entries[j].ssid)return false;
    }
    return true;
}
bool read_array(const cJSON* array,std::vector<SsidItem>& entries) {
    if(!cJSON_IsArray(array) || cJSON_GetArraySize(array)>10)return false;
    for(auto item=array->child;item;item=item->next){
        auto ssid=cJSON_GetObjectItemCaseSensitive(item,"ssid");
        auto password=cJSON_GetObjectItemCaseSensitive(item,"password");
        auto channel=cJSON_GetObjectItemCaseSensitive(item,"channel");
        if(!cJSON_IsObject(item) || cJSON_GetArraySize(item)!=3 || !cJSON_IsString(ssid) ||
           !cJSON_IsString(password) || !cJSON_IsNumber(channel) || !std::isfinite(channel->valuedouble) ||
           channel->valuedouble<0 || channel->valuedouble>255 || std::floor(channel->valuedouble)!=channel->valuedouble)return false;
        entries.push_back({ssid->valuestring,password->valuestring,static_cast<uint8_t>(channel->valuedouble)});
    }
    return valid(entries);
}
bool add_array(cJSON* root,const char* name,const std::vector<SsidItem>& entries) {
    auto array=cJSON_AddArrayToObject(root,name);if(!array)return false;
    for(const auto& entry:entries){
        auto item=cJSON_CreateObject();if(!item)return false;
        if(!cJSON_AddItemToArray(array,item)){cJSON_Delete(item);return false;}
        if(!cJSON_AddStringToObject(item,"ssid",entry.ssid.c_str()) ||
           !cJSON_AddStringToObject(item,"password",entry.password.c_str()) ||
           !cJSON_AddNumberToObject(item,"channel",entry.channel))return false;
    }
    return true;
}
bool legacy(std::vector<SsidItem>& entries) {
    Store store;auto result=nvs_open("wifi",NVS_READONLY,&store.handle);
    if(result==ESP_ERR_NVS_NOT_FOUND)return true;
    if(result!=ESP_OK)return false;
    for(int i=0;i<10;++i){
        std::string suffix=i?std::to_string(i):"";
        char ssid[33]={},password[65]={};uint8_t channel=0;size_t length=sizeof(ssid);
        result=nvs_get_str(store.handle,("ssid"+suffix).c_str(),ssid,&length);
        if(result==ESP_ERR_NVS_NOT_FOUND){
            size_t orphan=0;
            if(nvs_get_str(store.handle,("password"+suffix).c_str(),nullptr,&orphan)!=ESP_ERR_NVS_NOT_FOUND ||
               nvs_get_u8(store.handle,("channel"+suffix).c_str(),&channel)!=ESP_ERR_NVS_NOT_FOUND)return false;
            continue;
        }
        if(result!=ESP_OK || !length || length>sizeof(ssid) || ssid[length-1]!=0 || std::strlen(ssid)!=length-1)return false;
        length=sizeof(password);
        if(nvs_get_str(store.handle,("password"+suffix).c_str(),password,&length)!=ESP_OK ||
           !length || length>sizeof(password) || password[length-1]!=0 || std::strlen(password)!=length-1)return false;
        result=nvs_get_u8(store.handle,("channel"+suffix).c_str(),&channel);
        if(result!=ESP_OK && result!=ESP_ERR_NVS_NOT_FOUND)return false;
        entries.push_back({ssid,password,channel});
    }
    return valid(entries);
}
}

bool load(std::vector<SsidItem>& entries) {
    std::vector<SsidItem> loaded,previous;
    Store store;auto result=nvs_open("ampve_wifi",NVS_READONLY,&store.handle);
    bool use_legacy=result==ESP_ERR_NVS_NOT_FOUND;
    if(result!=ESP_OK && !use_legacy)return false;
    size_t size=0;
    if(!use_legacy){
        result=nvs_get_blob(store.handle,"networks",nullptr,&size);
        use_legacy=result==ESP_ERR_NVS_NOT_FOUND;
        if(result!=ESP_OK && !use_legacy)return false;
    }
    if(use_legacy){if(!legacy(loaded))return false;entries=std::move(loaded);return true;}
    if(size<2 || size>kLimit)return false;
    std::vector<char> data(size);
    if(nvs_get_blob(store.handle,"networks",data.data(),&size)!=ESP_OK || size!=data.size() || data.back()!=0)return false;
    const char* end=nullptr;
    Json root(cJSON_ParseWithLengthOpts(data.data(),data.size(),&end,true),cJSON_Delete);
    if(!root || end!=data.data()+data.size()-1 || !cJSON_IsObject(root.get()) || cJSON_GetArraySize(root.get())!=3)return false;
    std::unique_ptr<char,decltype(&cJSON_free)> canonical(cJSON_PrintUnformatted(root.get()),cJSON_free);
    if(!canonical || std::strlen(canonical.get())!=data.size()-1 || std::memcmp(canonical.get(),data.data(),data.size())!=0)return false;
    auto schema=cJSON_GetObjectItemCaseSensitive(root.get(),"schema");
    if(!cJSON_IsNumber(schema) || schema->valuedouble!=1 ||
       !read_array(cJSON_GetObjectItemCaseSensitive(root.get(),"active"),loaded) ||
       !read_array(cJSON_GetObjectItemCaseSensitive(root.get(),"previous"),previous))return false;
    entries=std::move(loaded);return true;
}

bool save(const std::vector<SsidItem>& entries,const std::vector<SsidItem>& previous) {
    if(!valid(entries) || !valid(previous))return false;
    Json root(cJSON_CreateObject(),cJSON_Delete);
    if(!root || !cJSON_AddNumberToObject(root.get(),"schema",1) ||
       !add_array(root.get(),"active",entries) || !add_array(root.get(),"previous",previous))return false;
    std::unique_ptr<char,decltype(&cJSON_free)> encoded(cJSON_PrintUnformatted(root.get()),cJSON_free);
    if(!encoded)return false;
    size_t size=std::strlen(encoded.get())+1;if(size>kLimit)return false;
    Store store;
    if(nvs_open("ampve_wifi",NVS_READWRITE,&store.handle)!=ESP_OK)return false;
    return nvs_set_blob(store.handle,"networks",encoded.get(),size)==ESP_OK && nvs_commit(store.handle)==ESP_OK;
}
}
