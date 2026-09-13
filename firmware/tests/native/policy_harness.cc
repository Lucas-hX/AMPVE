// Host-only executable: synthetic public trust and signed fixtures, never a device API.
#include "ota_policy.h"
#include "cJSON.h"
#include "sodium.h"
#include <fstream>
#include <iostream>
#include <iterator>
std::string read(const char* path) {
    std::ifstream file(path); return {std::istreambuf_iterator<char>(file), {}};
}
int main(int argc, char** argv) {
    if (argc != 4) return 2;
    auto raw=read(argv[2]); auto root=cJSON_Parse(raw.c_str()); if(!root)return 2;
    auto str=[&](const char* key){return std::string(cJSON_GetObjectItem(root,key)->valuestring);};
    auto num=[&](const char* key){return cJSON_GetObjectItem(root,key)->valuedouble;};
    ampve::OtaContext context;
    context.profile=str("profile");context.profile_id=str("profile_id");context.layout_id=str("layout_id");
    context.lineage=str("lineage");context.profile_version=num("profile_version");context.chip_revision=num("chip_revision");
    context.flash_bytes=num("flash_bytes");context.slot_capacity=num("slot_capacity");context.now_utc=num("now_utc");
    context.confirmed_sequence=num("confirmed_sequence");context.minimum_sequence=num("minimum_sequence");
    context.running_app_sha256=str("running_app_sha256");context.bootloader_sha256=str("bootloader_sha256");
    context.table_sha256=str("table_sha256");
    ampve::OtaPublisher publisher;
    publisher.id=str("key_id");publisher.development_ota=num("authorized");publisher.revoked=num("revoked");
    auto hex=str("public_key");
    if(sodium_hex2bin(publisher.public_key,32,hex.c_str(),hex.size(),nullptr,nullptr,nullptr)!=0)return 2;
    if(num("with_key"))context.publishers.push_back(publisher);
    if(num("release_revoked"))context.revoked_releases.push_back(argv[3]);
    cJSON_Delete(root);
    ampve::OtaPolicy output;output.release_id="must clear on failure";
    bool accepted=ampve::verify_ota_policy(read(argv[1]),argv[3],context,output);
    if(!accepted && !output.release_id.empty())return 3;
    std::cout<<(accepted?"accepted":"refused")<<"\n";
}
