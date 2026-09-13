#include "ampve_credentials.h"
#include "nvs.h"
#include "cJSON.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <map>
#include <thread>
#include <vector>

struct Value {int type;std::string data;};
static std::map<std::string,Value> legacy;
static std::string blob;
static std::string fault;
static int writes=0,commits=0,opened=0,closed=0;
int nvs_open(const char* name,int mode,nvs_handle_t* h) {
    if((mode==NVS_READWRITE && fault=="open_write") || (mode==NVS_READONLY && fault=="open_read"))return ESP_FAIL;
    if(std::string(name)=="wifi") {if(legacy.empty())return ESP_ERR_NVS_NOT_FOUND;*h=1;}
    else {assert(std::string(name)=="ampve_wifi");if(blob.empty() && mode==NVS_READONLY)return ESP_ERR_NVS_NOT_FOUND;*h=2;}
    ++opened;return ESP_OK;
}
void nvs_close(nvs_handle_t h){assert(h==1 || h==2);++closed;}
int nvs_get_str(nvs_handle_t h,const char* key,char* p,size_t* n){
    assert(h==1);if(fault=="legacy_read")return ESP_FAIL;
    auto it=legacy.find(key);if(it==legacy.end())return ESP_ERR_NVS_NOT_FOUND;
    if(it->second.type!=1)return ESP_FAIL;
    auto size=it->second.data.size()+1;
    if(p){if(*n<size)return ESP_FAIL;memcpy(p,it->second.data.c_str(),size);}
    *n=size;return ESP_OK;
}
int nvs_get_u8(nvs_handle_t h,const char* key,uint8_t* p){
    assert(h==1);auto it=legacy.find(key);if(it==legacy.end())return ESP_ERR_NVS_NOT_FOUND;
    if(it->second.type!=2)return ESP_FAIL;
    *p=static_cast<uint8_t>(std::stoi(it->second.data));return ESP_OK;
}
int nvs_get_blob(nvs_handle_t h,const char* key,void* p,size_t* n){
    assert(h==2 && !strcmp(key,"networks"));if(fault=="blob_read")return ESP_FAIL;
    if(blob.empty())return ESP_ERR_NVS_NOT_FOUND;
    if(p){if(*n<blob.size())return ESP_FAIL;memcpy(p,blob.data(),blob.size());}
    *n=blob.size();return ESP_OK;
}
int nvs_set_blob(nvs_handle_t h,const char* key,const void* p,size_t n){
    assert(h==2 && !strcmp(key,"networks"));++writes;
    if(fault=="set_before")return ESP_FAIL;
    blob.assign(static_cast<const char*>(p),n);
    return fault=="set_after"?ESP_FAIL:ESP_OK;
}
int nvs_commit(nvs_handle_t h){assert(h==2);++commits;return fault=="commit"?ESP_FAIL:ESP_OK;}
static void seed(){legacy["ssid"]={1,"Fixture network"};legacy["password"]={1,"old-fixture-password"};legacy["channel"]={2,"6"};}
static void retained(){
    assert(legacy.at("password").data=="old-fixture-password");
    auto root=cJSON_Parse(blob.c_str());assert(root);
    auto previous=cJSON_GetObjectItemCaseSensitive(root,"previous");
    auto item=cJSON_GetArrayItem(previous,0);
    assert(!strcmp(cJSON_GetObjectItemCaseSensitive(item,"password")->valuestring,"old-fixture-password"));
    cJSON_Delete(root);
}
int main(int argc,char** argv){
    assert(argc==2);std::string scenario=argv[1];seed();
    if(scenario=="fresh")legacy.clear();
    if(scenario=="orphan")legacy.erase("ssid");
    if(scenario=="missing_password")legacy.erase("password");
    if(scenario=="wrong_type")legacy["ssid"].type=2;
    if(scenario=="long_legacy")legacy["ssid"].data=std::string(33,'x');
    if(scenario=="open_read" || scenario=="legacy_read")fault=scenario;
    if(scenario=="malformed")blob="broken";
    if(scenario=="oversized")blob=std::string(16385,'x');
    if(scenario=="trailing" || scenario=="nul_escape" || scenario=="blob_read" || scenario=="schema" || scenario=="fraction" || scenario=="duplicate" || scenario=="missing_previous"){
        assert(ampve_wifi::save({{"Fixture network","old-fixture-password",6}},{}));writes=commits=0;
        if(scenario=="trailing")blob+='x';
        if(scenario=="nul_escape")blob.insert(blob.find("old-fixture"),"\\u0000");
        if(scenario=="blob_read")fault=scenario;
        if(scenario=="schema" || scenario=="fraction" || scenario=="duplicate" || scenario=="missing_previous"){
            auto root=cJSON_Parse(blob.c_str());assert(root);
            if(scenario=="schema")cJSON_SetNumberValue(cJSON_GetObjectItem(root,"schema"),2);
            if(scenario=="fraction")cJSON_SetNumberValue(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(root,"active"),0),"channel"),6.5);
            if(scenario=="duplicate"){auto entries=cJSON_GetObjectItem(root,"active");assert(cJSON_AddItemToArray(entries,cJSON_Duplicate(cJSON_GetArrayItem(entries,0),true)));}
            if(scenario=="missing_previous")cJSON_DeleteItemFromObject(root,"previous");
            char* raw=cJSON_PrintUnformatted(root);assert(raw);blob.assign(raw,strlen(raw)+1);cJSON_free(raw);cJSON_Delete(root);
        }
    }
    auto& manager=SsidManager::GetInstance();
    bool invalid=scenario=="orphan" || scenario=="missing_password" || scenario=="wrong_type" || scenario=="long_legacy" ||
        scenario=="open_read" || scenario=="legacy_read" || scenario=="malformed" || scenario=="oversized" ||
        scenario=="trailing" || scenario=="nul_escape" || scenario=="blob_read" || scenario=="schema" || scenario=="fraction" || scenario=="duplicate" || scenario=="missing_previous";
    if(invalid){assert(!manager.IsStorageReady());assert(!manager.AddSsid("New","fixture-new",1));assert(writes==0);}
    else if(scenario=="open_write" || scenario=="set_before" || scenario=="set_after" || scenario=="commit"){
        fault=scenario;assert(!manager.AddSsid("Fixture network","new-fixture-password",1));
        assert(!manager.IsStorageReady() && manager.GetSsidList()[0].password=="old-fixture-password");
        int count=writes;assert(!manager.Clear() && !manager.AddSsid("Other","x",1) && writes==count);
        if(scenario=="set_after" || scenario=="commit")retained();
        else assert(blob.empty());
    }else if(scenario=="bounds"){
        std::vector<SsidItem> entries;
        for(int i=0;i<10;++i)entries.push_back({std::string(31,'\x01')+char('A'+i),std::string(64,'\x02'),6});
        assert(ampve_wifi::save(entries,entries) && blob.size()<=16384);
        std::vector<SsidItem> loaded;assert(ampve_wifi::load(loaded) && loaded.size()==10 && loaded[0].password==entries[0].password);
        int before=writes;entries[0].ssid=std::string(33,'x');assert(!ampve_wifi::save(entries,{}) && writes==before);
        entries[0].ssid="X";entries[0].password=std::string(65,'x');assert(!ampve_wifi::save(entries,{}) && writes==before);
    }else if(scenario=="concurrent"){
        std::vector<std::thread> threads;
        for(int i=0;i<4;++i)threads.emplace_back([i,&manager]{for(int j=0;j<10;++j){assert(manager.AddSsid("Test "+std::to_string(i),"fixture",1));auto list=manager.GetSsidList();assert(!list.empty());}});
        for(auto& thread:threads){thread.join();}
        assert(manager.GetSsidList().size()==5);
    }else{
        assert(manager.IsStorageReady());assert(manager.AddSsid("Fixture network","new-fixture-password",1));
        if(scenario!="fresh")retained();
        std::vector<SsidItem> loaded;assert(ampve_wifi::load(loaded) && loaded[0].password=="new-fixture-password");
        assert(manager.AddSsid("Other","",0));assert(manager.SetDefaultSsid(1));assert(manager.UpdateSsidChannel("Other",11));
        assert(!manager.RemoveSsid(50) && !manager.SetDefaultSsid(-1));assert(manager.RemoveSsid(0));
        assert(manager.Clear() && manager.GetSsidList().empty());assert(ampve_wifi::load(loaded) && loaded.empty());
        assert(legacy.empty() || legacy.at("password").data=="old-fixture-password");
    }
    assert(opened==closed);std::cout<<"Credential storage scenario passed: "<<scenario<<"\n";
}
