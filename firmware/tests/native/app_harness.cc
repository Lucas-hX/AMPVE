// Host fixture for the actual signed v1 package verifier and RAM transition logic.
#include "app_package.h"
#include "app_runtime.h"
#include "cJSON.h"
#include "sodium.h"
#include <fstream>
#include <iostream>
#include <iterator>

std::string read(const char* path) {
    std::ifstream file(path);return {std::istreambuf_iterator<char>(file),{}};
}
int main(int argc,char** argv) {
    if(argc!=5)return 2;
    auto context_json=cJSON_Parse(read(argv[2]).c_str());if(!context_json)return 2;
    auto text=[&](const char* key){auto field=cJSON_GetObjectItemCaseSensitive(context_json,key);
        return std::string(cJSON_IsString(field)&&field->valuestring?field->valuestring:"");};
    auto value=[&](const char* key){auto field=cJSON_GetObjectItemCaseSensitive(context_json,key);
        return cJSON_IsNumber(field)?field->valuedouble:0.0;};
    ampve::OtaContext context;
    context.profile_id=text("profile_id");context.layout_id=text("layout_id");
    context.profile_version=value("profile_version");context.chip_revision=value("chip_revision");
    context.flash_bytes=value("flash_bytes");context.now_utc=value("now_utc");
    ampve::OtaPublisher publisher;
    publisher.id=text("key_id");publisher.development_ota=value("authorized");
    publisher.revoked=value("revoked");auto hex=text("public_key");
    if(sodium_hex2bin(publisher.public_key,32,hex.c_str(),hex.size(),nullptr,nullptr,nullptr)!=0)return 2;
    context.publishers.push_back(publisher);cJSON_Delete(context_json);
    ampve::AppPackage package;
    const bool accepted=ampve::verify_app_package(read(argv[1]),argv[3],context,33554432,package);
    if(std::string(argv[4])=="runtime") {
        if(!accepted)return 3;
        ampve::AppRuntime runtime;
        if(!runtime.stage(package) || runtime.activate(false) || !runtime.activate(true) ||
           runtime.active().id!=package.id)return 3;
        if(runtime.stage(package)==false || runtime.staged().id!="")return 3;
        if(runtime.disable(false) || runtime.active().id!=package.id ||
           !runtime.disable(true) || !runtime.active().id.empty() ||
           !runtime.rollback(true) || runtime.active().id!=package.id)return 3;
        if(!runtime.revoke(package.id,true) || !runtime.active().id.empty())return 3;
        std::cout<<"runtime-safe\n";return 0;
    }
    std::cout<<(accepted?"accepted":"refused")<<"\n";
    return 0;
}
