#include "ota_client.h"
#include "cJSON.h"
#include <cmath>
#include <cstring>
#include <memory>
#include <set>
#include <utility>

namespace ampve {
namespace {
using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
bool unique_keys(cJSON* node) {
    std::set<std::string> keys;
    for(auto child=node->child;child;child=child->next){
        if(cJSON_IsObject(node)&&(!child->string||!keys.insert(child->string).second))return false;
        if(!unique_keys(child))return false;
    }
    return true;
}
Json parse(const std::string& raw,size_t maximum=32768) {
    if(raw.empty() || raw.size()>maximum || raw.find('\0')!=std::string::npos || raw.find("\\u0000")!=std::string::npos) return Json(nullptr,cJSON_Delete);
    bool quoted=false,escaped=false;int depth=0;
    for(char c:raw){
        if(quoted){if(escaped)escaped=false;else if(c=='\\')escaped=true;else if(c=='"')quoted=false;}
        else if(c=='"')quoted=true;
        else if(c=='{'||c=='['){if(++depth>8)return Json(nullptr,cJSON_Delete);}
        else if(c=='}'||c==']'){if(--depth<0)return Json(nullptr,cJSON_Delete);}
    }
    if(quoted||depth)return Json(nullptr,cJSON_Delete);
    const char* end=nullptr;
    Json result(cJSON_ParseWithLengthOpts(raw.c_str(),raw.size()+1,&end,true),cJSON_Delete);
    if(result && !unique_keys(result.get()))result.reset();
    return result;
}
std::string text(cJSON* root,const char* key) {
    auto item=cJSON_GetObjectItemCaseSensitive(root,key);
    return cJSON_IsString(item)&&item->valuestring?item->valuestring:"";
}
std::string encode(cJSON* root) {
    char* raw=cJSON_PrintUnformatted(root);std::string result=raw?raw:"";cJSON_free(raw);return result;
}
bool number(cJSON* root,const char* key,uint32_t max,uint32_t& value) {
    auto item=cJSON_GetObjectItemCaseSensitive(root,key);
    if(!cJSON_IsNumber(item)||!std::isfinite(item->valuedouble)||item->valuedouble<0||item->valuedouble>max||std::floor(item->valuedouble)!=item->valuedouble)return false;
    value=static_cast<uint32_t>(item->valuedouble);return true;
}
uint32_t num(cJSON* root,const char* key) {uint32_t value=0;number(root,key,2147483647,value);return value;}
bool identifier(const std::string& value,bool uuid=false) {
    if(value.size()!=(uuid?36u:64u))return false;
    for(size_t i=0;i<value.size();++i){char c=value[i];if(uuid&&(i==8||i==13||i==18||i==23)){if(c!='-')return false;}
        else if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;}
    return true;
}
void string(cJSON* root,const char* key,const std::string& value) {cJSON_DeleteItemFromObject(root,key);cJSON_AddStringToObject(root,key,value.c_str());}
void integer(cJSON* root,const char* key,uint32_t value) {cJSON_DeleteItemFromObject(root,key);cJSON_AddNumberToObject(root,key,value);}
bool valid_journal(cJSON* root) {
    uint32_t seq,size,bytes,slot,target_sequence;
    if(!cJSON_IsObject(root)||num(root,"schema")!=1||!identifier(text(root,"device"),true)||!identifier(text(root,"job"),true)||
       !identifier(text(root,"release"))||!identifier(text(root,"previous"))||!identifier(text(root,"target"))||
       !number(root,"sequence",128,seq)||!number(root,"size",4194304,size)||size<24||
       !number(root,"bytes",size,bytes)||!number(root,"slot",33554432,slot)||!slot||
       !number(root,"target_sequence",2147483647,target_sequence)||!target_sequence)return false;
    auto pending=cJSON_GetObjectItemCaseSensitive(root,"pending");
    if(cJSON_GetArraySize(root)!=(pending?13:12))return false;
    if(pending && (!cJSON_IsObject(pending)||cJSON_GetArraySize(pending)!=7||num(pending,"sequence")!=seq||
       num(pending,"bytes_written")!=bytes||text(pending,"release_id")!=text(root,"release")||
       text(pending,"state")!=text(root,"state")||!cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(pending,"boot_confirmed"))||
       text(pending,"app_sha256")!=text(root,text(root,"state")=="confirmed"?"target":"previous")))return false;
    auto state=text(root,"state");
    return state=="queued"||state=="downloading"||state=="verifying"||state=="rebooting"||
           state=="confirmed"||state=="rolled_back"||state=="failed";
}
bool terminal(const std::string& state) {return state=="confirmed"||state=="rolled_back"||state=="failed";}
std::string path(cJSON* root) {return text(root,"device")+"/updates/"+text(root,"job")+"/";}
}

bool OtaClient::persist() {
    if(journal_.size()>2048 || !port_.save(journal_)){stopped_=true;port_.status("Update storage error. Keep recovery files.");return false;}
    return true;
}
bool OtaClient::flush() {
    auto root=parse(journal_,2048);if(!root || !valid_journal(root.get()))return false;
    auto pending=cJSON_GetObjectItemCaseSensitive(root.get(),"pending");
    if(!cJSON_IsObject(pending))return true;
    std::string reply;
    int status=port_.post(path(root.get())+"report/",encode(pending),reply);
    if(status==409){
        // Reconcile a definitive rejection separately from a lost response. Never reuse
        // a denied boot/download authorization merely because an earlier copy was accepted.
        std::string query="{\"release_id\":\""+text(root.get(),"release")+"\"}";
        if(port_.post(path(root.get())+"status/",query,reply)!=200)return false;
        auto remote=parse(reply);
        if(!remote || text(remote.get(),"deployment_id")!=text(root.get(),"job") || text(remote.get(),"release_id")!=text(root.get(),"release"))return false;
        auto actual=text(remote.get(),"state");uint32_t sequence=num(remote.get(),"sequence");
        if(actual=="cancelled" && (text(root.get(),"state")=="downloading" || text(root.get(),"state")=="failed") && num(root.get(),"bytes")==0){journal_.clear();interrupted_=false;persist();return false;}
        if(sequence!=num(root.get(),"sequence") && sequence+1!=num(root.get(),"sequence"))return false;
        if(actual!="queued"&&actual!="downloading"&&actual!="verifying"&&actual!="rebooting")return false;
        string(root.get(),"state",actual);integer(root.get(),"sequence",sequence);integer(root.get(),"bytes",num(remote.get(),"bytes_written"));
        cJSON_DeleteItemFromObject(root.get(),"pending");journal_=encode(root.get());interrupted_=true;persist();return false;
    }
    if(status!=200)return false;
    auto ack=parse(reply);
    if(!ack || text(ack.get(),"release_id")!=text(root.get(),"release") || text(ack.get(),"deployment_id")!=text(root.get(),"job") ||
       num(ack.get(),"sequence")!=num(root.get(),"sequence") || text(ack.get(),"state")!=text(root.get(),"state"))return false;
    cJSON_DeleteItemFromObject(root.get(),"pending");journal_=encode(root.get());return persist();
}
bool OtaClient::report(const char* state,size_t bytes,const char* error) {
    auto root=parse(journal_,2048);if(!root || !valid_journal(root.get()) || bytes>num(root.get(),"size") || num(root.get(),"sequence")>=128)return false;
    // A lost acknowledgement must be retried verbatim before advancing the sequence.
    if(cJSON_GetObjectItemCaseSensitive(root.get(),"pending"))return false;
    string(root.get(),"state",state);integer(root.get(),"sequence",num(root.get(),"sequence")+1);integer(root.get(),"bytes",bytes);
    auto payload=cJSON_AddObjectToObject(root.get(),"pending");
    cJSON_AddStringToObject(payload,"release_id",text(root.get(),"release").c_str());
    cJSON_AddNumberToObject(payload,"sequence",num(root.get(),"sequence"));cJSON_AddStringToObject(payload,"state",state);
    cJSON_AddNumberToObject(payload,"bytes_written",bytes);cJSON_AddBoolToObject(payload,"boot_confirmed",true);
    cJSON_AddStringToObject(payload,"app_sha256",text(root.get(),std::strcmp(state,"confirmed")==0?"target":"previous").c_str());
    cJSON_AddStringToObject(payload,"error_code",error);
    journal_=encode(root.get());return persist()&&flush();
}
bool OtaClient::progress(size_t bytes) {
    auto root=parse(journal_,2048);if(!root || !valid_journal(root.get()) || text(root.get(),"state")!="downloading")return false;
    const std::string progress="Firmware update: "+std::to_string(bytes*100/num(root.get(),"size"))+"% written. Keep power connected.";
    port_.status(progress.c_str());
    if(bytes==num(root.get(),"size") || bytes>=num(root.get(),"bytes")+262144)
        return report("downloading",bytes);
    return true;
}
bool OtaClient::approved(OtaPolicy& policy) {
    OtaContext context;if(!port_.context(context))return false;
    auto root=parse(journal_,2048);if(!root)return false;
    auto payload=Json(cJSON_CreateObject(),cJSON_Delete);
    cJSON_AddNumberToObject(payload.get(),"protocol",1);cJSON_AddBoolToObject(payload.get(),"boot_confirmed",true);
    cJSON_AddStringToObject(payload.get(),"app_sha256",context.running_app_sha256.c_str());
    std::string reply;if(port_.post(device_+"/updates/poll/",encode(payload.get()),reply)!=200)return false;
    auto response=parse(reply);auto job=cJSON_GetObjectItemCaseSensitive(response.get(),"deployment");
    if(!cJSON_IsObject(job)||text(job,"deployment_id")!=text(root.get(),"job")||text(job,"release_id")!=text(root.get(),"release"))return false;
    auto envelope=cJSON_GetObjectItemCaseSensitive(job,"envelope");
    if(!verify_ota_policy(encode(envelope),text(root.get(),"release"),context,policy))return false;
    return policy.app_sha256==text(root.get(),"target")&&policy.app_size==num(root.get(),"size")&&policy.sequence==num(root.get(),"target_sequence");
}
void OtaClient::tick(const std::string& device) {
    if(stopped_||!identifier(device,true))return;
    device_=device;
    if(!initialized_){
        if(!port_.load(journal_)){stopped_=true;port_.status("Update journal unavailable. Local recovery required.");return;}
        initialized_=true;interrupted_=!journal_.empty();
    }
    OtaContext context;if(!port_.context(context))return;
    if(journal_.empty()) {
        if(context.publishers.empty()||!context.confirmed_sequence)return;
        auto payload=Json(cJSON_CreateObject(),cJSON_Delete);
        cJSON_AddNumberToObject(payload.get(),"protocol",1);cJSON_AddBoolToObject(payload.get(),"boot_confirmed",true);
        cJSON_AddStringToObject(payload.get(),"app_sha256",context.running_app_sha256.c_str());
        std::string reply;if(port_.post(device+"/updates/poll/",encode(payload.get()),reply)!=200)return;
        auto response=parse(reply);auto job=cJSON_GetObjectItemCaseSensitive(response.get(),"deployment");
        if(!cJSON_IsObject(job)||text(job,"state")!="queued"||!identifier(text(job,"deployment_id"),true))return;
        OtaPolicy policy;if(!verify_ota_policy(encode(cJSON_GetObjectItemCaseSensitive(job,"envelope")),text(job,"release_id"),context,policy)){
            port_.status("Firmware update refused: trust or compatibility check failed.");return;}
        uint32_t slot=port_.inactive_slot();if(!slot)return;
        auto root=Json(cJSON_CreateObject(),cJSON_Delete);
        for(auto item: {std::pair<const char*,std::string>{"device",device},{"job",text(job,"deployment_id")},{"release",policy.release_id},
            {"previous",context.running_app_sha256},{"target",policy.app_sha256},{"state","queued"}})string(root.get(),item.first,item.second);
        integer(root.get(),"schema",1);integer(root.get(),"slot",slot);integer(root.get(),"size",policy.app_size);integer(root.get(),"target_sequence",policy.sequence);
        integer(root.get(),"sequence",0);integer(root.get(),"bytes",0);journal_=encode(root.get());if(!persist())return;
    }
    auto root=parse(journal_,2048);
    if(!root||!valid_journal(root.get())||text(root.get(),"device")!=device){stopped_=true;port_.status("Update journal mismatch. Local recovery required.");return;}
    auto state=text(root.get(),"state");
    if(context.running_app_sha256!=text(root.get(),"previous")&&context.running_app_sha256!=text(root.get(),"target")){
        stopped_=true;port_.status("Running firmware differs from the update journal.");return;}
    if(!flush())return;
    if(journal_.empty())return;
    root=parse(journal_,2048);state=text(root.get(),"state");
    if(terminal(state)) {
        if(state=="confirmed"&&!port_.advance_sequence(num(root.get(),"target_sequence"))){stopped_=true;return;}
        journal_.clear();persist();interrupted_=false;port_.status("Firmware outcome reported to your dashboard.");return;
    }
    if(state=="rebooting" && (interrupted_||context.running_app_sha256==text(root.get(),"target"))) {
        if(context.running_app_sha256==text(root.get(),"target"))report("confirmed",num(root.get(),"size"));
        else if(port_.target_failed(num(root.get(),"slot")))report("rolled_back",num(root.get(),"size"),"boot_failed");
        else report("failed",num(root.get(),"size"),"storage");
        return;
    }
    if(interrupted_) {report("failed",num(root.get(),"bytes"),"network");return;}
    if(state=="queued") {if(!report("downloading",0))return;state="downloading";}
    OtaPolicy policy;
    if(!approved(policy)){report("failed",num(root.get(),"bytes"),"approval_unavailable");return;}
    if(state=="downloading") {
        bool success=port_.download(path(root.get())+"artifact/",policy.release_id,policy,num(root.get(),"slot"));
        if(stopped_)return;
        // A progress report with a lost response is retained verbatim before reporting failure.
        if(!flush()) {interrupted_=true;return;}
        root=parse(journal_,2048);
        if(!success){report("failed",num(root.get(),"bytes"),port_.failure());return;}
        if(!report("verifying",policy.app_size))return;
    }
    port_.status("Download complete. Verifying firmware before restart.");
    if(!approved(policy)){report("failed",num(root.get(),"bytes"),"approval_unavailable");return;}
    if(!port_.verify_target(num(root.get(),"slot"),policy.app_sha256,policy.app_size)){
        report("failed",policy.app_size,"hash_mismatch");return;}
    if(state!="rebooting" && !report("rebooting",policy.app_size))return;
    // Authorization acknowledgement is persisted before selecting a different boot slot.
    int selection=port_.select(num(root.get(),"slot"),policy.expires_at);
    if(selection<0){stopped_=true;port_.status("Boot selection uncertain. Retain power and recovery files; inspect locally.");return;}
    if(selection==0){report("failed",policy.app_size,port_.failure());return;}
    port_.status("Firmware verified. Restarting; keep power connected.");port_.restart();
}
}
