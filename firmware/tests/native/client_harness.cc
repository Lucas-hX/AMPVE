// Actual OTA state machine against a persistent in-memory server/flash boundary, never hardware.
#include "ota_client.h"
#include "cJSON.h"
#include "sodium.h"
#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
std::string read(const char* path){std::ifstream file(path);return {std::istreambuf_iterator<char>(file),{}};}
std::string str(cJSON* root,const char* key){auto v=cJSON_GetObjectItem(root,key);return cJSON_IsString(v)?v->valuestring:"";}
int num(cJSON* root,const char* key){auto v=cJSON_GetObjectItem(root,key);return cJSON_IsNumber(v)?v->valueint:0;}
std::string encode(cJSON* root){char* p=cJSON_PrintUnformatted(root);std::string s=p?p:"";cJSON_free(p);return s;}
struct Port:ampve::OtaPort {
    ampve::OtaContext ctx;std::string envelope,identity,journal,scenario,last_report;
    std::string server_state="queued";int server_sequence=0,downloads=0,saves=0;bool selected=false,restarted=false,lost=false;
    uint32_t floor=1;std::string previous,target;size_t size=524288; ampve::OtaClient* engine=nullptr;
    const std::string device="11111111-1111-1111-1111-111111111111",job="22222222-2222-2222-2222-222222222222";
    bool context(ampve::OtaContext& out)override{out=ctx;return true;}
    bool load(std::string& out)override{out=journal;return true;}
    bool save(const std::string& value)override{++saves;if(scenario=="save_fail" || (scenario=="save_ack_fail"&&saves==3))return false;journal=value;return true;}
    bool advance_sequence(uint32_t value)override{assert(value>=floor);floor=value;return true;}
    int post(const std::string& path,const std::string& body,std::string& reply)override{
        auto out=cJSON_CreateObject();
        if(path==device+"/updates/poll/"){
            auto deployment=cJSON_AddObjectToObject(out,"deployment");
            cJSON_AddStringToObject(deployment,"deployment_id",job.c_str());cJSON_AddStringToObject(deployment,"release_id",identity.c_str());
            cJSON_AddStringToObject(deployment,"state",server_state.c_str());cJSON_AddItemToObject(deployment,"envelope",cJSON_Parse(envelope.c_str()));
        }else if(path==device+"/updates/"+job+"/status/"){
            cJSON_AddStringToObject(out,"deployment_id",job.c_str());cJSON_AddStringToObject(out,"release_id",identity.c_str());
            cJSON_AddStringToObject(out,"state",server_state.c_str());cJSON_AddNumberToObject(out,"sequence",server_sequence);
            auto previous=cJSON_Parse(last_report.c_str());cJSON_AddNumberToObject(out,"bytes_written",num(previous,"bytes_written"));cJSON_Delete(previous);
        }else{
            assert(path==device+"/updates/"+job+"/report/");auto payload=cJSON_Parse(body.c_str());assert(payload);
            auto state=str(payload,"state");
            if((scenario=="reauthorization_denied"&&state=="rebooting") || (scenario=="revoked_after_lost_ack"&&state=="rebooting"&&lost)){
                cJSON_Delete(payload);cJSON_Delete(out);return 409;
            }
            if(scenario=="owner_cancel_race"&&state=="downloading"){
                server_state="cancelled";cJSON_Delete(payload);cJSON_Delete(out);return 409;
            }
            int sequence=num(payload,"sequence");assert(str(payload,"release_id")==identity);
            if(sequence==server_sequence)assert(last_report==body);
            else{
                assert(sequence==server_sequence+1);
                assert((server_state=="queued"&&(state=="downloading"||state=="failed")) ||
                    (server_state=="downloading"&&(state=="downloading"||state=="verifying"||state=="failed")) ||
                    (server_state=="verifying"&&(state=="rebooting"||state=="failed")) ||
                    (server_state=="rebooting"&&(state=="confirmed"||state=="rolled_back"||state=="failed")));
                assert(str(payload,"app_sha256")== (state=="confirmed"?target:previous));
                server_sequence=sequence;server_state=state;last_report=body;
            }
            cJSON_Delete(payload);
            cJSON_AddStringToObject(out,"deployment_id",job.c_str());cJSON_AddStringToObject(out,"release_id",identity.c_str());
            cJSON_AddStringToObject(out,"state",server_state.c_str());cJSON_AddNumberToObject(out,"sequence",server_sequence);
            bool lose=(scenario=="claim_ack_lost"&&server_sequence==1)||(scenario=="progress_ack_lost"&&server_sequence==2)||
                (scenario=="verify_ack_lost"&&state=="verifying")||(scenario=="reboot_ack_lost"&&state=="rebooting")||
                (scenario=="outcome_ack_lost"&&state=="confirmed")||(scenario=="revoked_after_lost_ack"&&state=="rebooting");
            if(lose&&!lost){lost=true;cJSON_Delete(out);return -1;}
        }
        reply=encode(out);cJSON_Delete(out);return 200;
    }
    uint32_t inactive_slot()override{return 0xa10000;}
    bool download(const std::string& path,const std::string& release,const ampve::OtaPolicy& policy,uint32_t slot)override{
        ++downloads;assert(path==device+"/updates/"+job+"/artifact/"&&release==identity&&slot==inactive_slot()&&policy.app_size==size);
        if(scenario=="network"||scenario=="cancel")return false;
        if(!engine->progress(262144))return false;
        if(scenario=="power_download")throw std::runtime_error("simulated power loss");
        return engine->progress(size);
    }
    const char* failure()override{return scenario=="cancel"?"local_cancelled":scenario=="select"?"image_rejected":"network";}
    bool verify_target(uint32_t slot,const std::string& hash,size_t bytes)override{assert(slot==inactive_slot()&&hash==target&&bytes==size);return scenario!="hash";}
    int select(uint32_t slot,int64_t expires_at)override{assert(slot==inactive_slot()&&expires_at>ctx.now_utc);if(scenario=="power_before_select")throw std::runtime_error("simulated power loss");if(scenario=="select_uncertain")return -1;if(scenario=="select")return 0;selected=true;return 1;}
    bool target_failed(uint32_t slot)override{assert(slot==inactive_slot());return scenario=="rollback";}
    void restart()override{restarted=true;}
    void status(const char*)override{}
};
int main(int argc,char** argv){
    assert(argc==5);Port port;port.envelope=read(argv[1]);port.identity=argv[3];port.scenario=argv[4];
    auto raw=read(argv[2]);auto c=cJSON_Parse(raw.c_str());auto& ctx=port.ctx;
    ctx.profile=str(c,"profile");ctx.profile_id=str(c,"profile_id");ctx.layout_id=str(c,"layout_id");ctx.lineage=str(c,"lineage");
    ctx.profile_version=num(c,"profile_version");ctx.chip_revision=num(c,"chip_revision");ctx.flash_bytes=num(c,"flash_bytes");
    ctx.slot_capacity=num(c,"slot_capacity");ctx.now_utc=cJSON_GetObjectItem(c,"now_utc")->valuedouble;
    ctx.minimum_sequence=1;ctx.confirmed_sequence=1;ctx.running_app_sha256=str(c,"running_app_sha256");port.previous=ctx.running_app_sha256;
    ctx.bootloader_sha256=str(c,"bootloader_sha256");ctx.table_sha256=str(c,"table_sha256");
    ampve::OtaPublisher publisher;publisher.id=str(c,"key_id");publisher.development_ota=true;
    auto hex=str(c,"public_key");assert(sodium_hex2bin(publisher.public_key,32,hex.c_str(),hex.size(),nullptr,nullptr,nullptr)==0);ctx.publishers.push_back(publisher);cJSON_Delete(c);
    ampve::OtaPolicy policy;assert(ampve::verify_ota_policy(port.envelope,port.identity,ctx,policy));port.target=policy.app_sha256;
    if(port.scenario=="corrupt_journal")port.journal="{";
    if(port.scenario=="deep_journal")port.journal=std::string(50,'[')+"0"+std::string(50,']');
    ampve::OtaClient engine(port);port.engine=&engine;
    for(int i=0;i<8&&!port.restarted&&port.server_state!="failed";++i){
        try{engine.tick(port.device);}catch(const std::runtime_error&){break;}
    }
    if(port.scenario=="corrupt_journal"||port.scenario=="deep_journal"){assert(!port.downloads&&!port.selected&&port.server_state=="queued"&&!port.journal.empty());}
    else if(port.scenario=="select_uncertain"){assert(!port.selected&&port.server_state=="rebooting"&&!port.journal.empty());}
    else if(port.scenario=="owner_cancel_race"){assert(!port.downloads&&!port.selected&&port.server_state=="cancelled"&&port.journal.empty());}
    else if(port.scenario=="save_fail"){assert(!port.downloads&&!port.selected&&port.server_state=="queued");}
    else if(port.scenario=="save_ack_fail"||port.scenario=="power_download"||port.scenario=="power_before_select"){
        auto downloads=port.downloads;port.scenario=port.scenario=="save_ack_fail"?"recovered":port.scenario;
        ampve::OtaClient rebooted(port);port.engine=&rebooted;
        for(int i=0;i<3;++i)rebooted.tick(port.device);
        assert(port.server_state=="failed"&&port.downloads==downloads&&!port.selected);
    }else if(port.scenario=="network"||port.scenario=="cancel"||port.scenario=="hash"||port.scenario=="select"||port.scenario=="progress_ack_lost"||port.scenario=="reauthorization_denied"||port.scenario=="revoked_after_lost_ack"){
        assert(port.server_state=="failed"&&!port.selected);
    }else{
        assert(port.restarted&&port.selected&&port.server_state=="rebooting");
        if(port.scenario!="rollback")ctx.running_app_sha256=port.target;
        ampve::OtaClient rebooted(port);port.engine=&rebooted;
        for(int i=0;i<3;++i)rebooted.tick(port.device);
        assert(port.server_state==(port.scenario=="rollback"?"rolled_back":"confirmed"));
        assert(port.floor==(port.scenario=="rollback"?1u:2u));
    }
    std::cout<<"OTA client scenario passed: "<<argv[4]<<"\n";
}
