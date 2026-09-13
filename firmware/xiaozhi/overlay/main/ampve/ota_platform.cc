#include "ota_platform.h"
#include "ota_client.h"
#include "publisher_trust.h"
#include "boards/waveshare/esp32-p4-wifi6-touch-lcd/config.h"
#include "profile.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_psram.h"
#include "esp_ota_ops.h"
#include "esp_image_format.h"
#include "esp_app_desc.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "nvs.h"
#include "sodium.h"
#include <algorithm>
#include <atomic>
#include <cstring>
#include <ctime>
#include <memory>

namespace {
std::atomic<bool> cancel_download{false};
bool flash_hash(uint32_t address,size_t size,std::string& hash) {
    hash.clear();if(!size || size>4194304)return false;
    std::unique_ptr<unsigned char[]> buffer(new(std::nothrow) unsigned char[4096]);if(!buffer)return false;
    crypto_hash_sha256_state state;crypto_hash_sha256_init(&state);
    for(size_t offset=0;offset<size;) {
        size_t count=std::min(size-offset,size_t(4096));
        if(esp_flash_read(nullptr,buffer.get(),address+offset,count)!=ESP_OK)return false;
        crypto_hash_sha256_update(&state,buffer.get(),count);offset+=count;
    }
    unsigned char digest[32];char hex[65];crypto_hash_sha256_final(&state,digest);sodium_bin2hex(hex,sizeof(hex),digest,sizeof(digest));hash=hex;return true;
}
const esp_partition_t* slot_at(uint32_t address) {
    for(auto subtype:{ESP_PARTITION_SUBTYPE_APP_OTA_0,ESP_PARTITION_SUBTYPE_APP_OTA_1}){
        auto slot=esp_partition_find_first(ESP_PARTITION_TYPE_APP,subtype,nullptr);
        if(slot && slot->address==address && !slot->encrypted && ((slot->address==AMPVE_OTA_0_OFFSET && slot->size==AMPVE_OTA_0_SIZE)||(slot->address==AMPVE_OTA_1_OFFSET && slot->size==AMPVE_OTA_1_SIZE)))return slot;
    }
    return nullptr;
}
class NativePort final: public ampve::OtaPort {
    nvs_handle_t nvs_=0;
    bool opened_=false;
    const char* error_="network";
    esp_http_client_handle_t http(const std::string& path) {
        // Paths are constructed from validated journal UUIDs; no response-supplied URL is followed.
        std::string url="https://ampve.com/api/devices/v1/"+path;
        esp_http_client_config_t config={};config.url=url.c_str();config.crt_bundle_attach=esp_crt_bundle_attach;
        config.timeout_ms=8000;config.disable_auto_redirect=true;config.buffer_size=4096;
        auto client=esp_http_client_init(&config);if(!client)return nullptr;
        esp_http_client_set_method(client,HTTP_METHOD_POST);esp_http_client_set_header(client,"Content-Type","application/json");
        esp_http_client_set_header(client,"Authorization",("Bearer "+token).c_str());return client;
    }
public:
    std::string token,running_hash;
    ampve::OtaClient* engine=nullptr;
    bool context(ampve::OtaContext& context) override {
        if(!opened_){if(nvs_open("ampve_ota",NVS_READWRITE,&nvs_)!=ESP_OK)return false;opened_=true;}
        context={};ampve_publisher_trust(context);
        uint32_t sequence=0;auto result=nvs_get_u32(nvs_,"sequence",&sequence);
        if(result!=ESP_OK && result!=ESP_ERR_NVS_NOT_FOUND)return false;
        context.confirmed_sequence=std::max(sequence,uint32_t(AMPVE_BUILD_SEQUENCE));context.now_utc=time(nullptr);
        context.running_app_sha256=running_hash;context.profile=AMPVE_INSTALLATION_PROFILE;
        context.profile_id=AMPVE_PROFILE_ID;context.profile_version=AMPVE_PROFILE_VERSION;context.layout_id=AMPVE_LAYOUT_ID;context.lineage=AMPVE_FIRMWARE_LINEAGE;
        esp_chip_info_t chip;esp_chip_info(&chip);uint32_t flash=0;
        if(chip.model!=CHIP_ESP32P4 || chip.revision!=103 || esp_flash_get_size(nullptr,&flash)!=ESP_OK || flash!=AMPVE_FLASH_BYTES || esp_psram_get_size()<AMPVE_MIN_PSRAM_BYTES)return false;
        context.chip_revision=chip.revision;context.flash_bytes=flash;context.slot_capacity=std::min(AMPVE_OTA_0_SIZE,AMPVE_OTA_1_SIZE);
        esp_partition_pos_t boot{0x2000,CONFIG_PARTITION_TABLE_OFFSET-0x2000};esp_image_metadata_t metadata={};
        return esp_image_verify(ESP_IMAGE_VERIFY_SILENT,&boot,&metadata)==ESP_OK &&
            flash_hash(boot.offset,metadata.image_len,context.bootloader_sha256) &&
            flash_hash(CONFIG_PARTITION_TABLE_OFFSET,0xc00,context.table_sha256);
    }
    bool load(std::string& value) override {
        if(!opened_){ampve::OtaContext ignored;if(!context(ignored))return false;}
        size_t size=0;auto error=nvs_get_str(nvs_,"journal",nullptr,&size);
        if(error==ESP_ERR_NVS_NOT_FOUND){value.clear();return true;}
        if(error!=ESP_OK || size>2049 || !size)return false;
        value.resize(size);if(nvs_get_str(nvs_,"journal",value.data(),&size)!=ESP_OK)return false;value.resize(size-1);return true;
    }
    bool save(const std::string& value) override {return opened_ && value.size()<=2048 && nvs_set_str(nvs_,"journal",value.c_str())==ESP_OK && nvs_commit(nvs_)==ESP_OK;}
    bool advance_sequence(uint32_t sequence) override {
        uint32_t current=0;auto error=nvs_get_u32(nvs_,"sequence",&current);if(error!=ESP_OK && error!=ESP_ERR_NVS_NOT_FOUND)return false;
        return sequence>=current && nvs_set_u32(nvs_,"sequence",sequence)==ESP_OK && nvs_commit(nvs_)==ESP_OK;
    }
    int post(const std::string& path,const std::string& body,std::string& reply) override {
        reply.clear();if(body.size()>2048)return -1;auto client=http(path);if(!client)return -1;
        int status=-1;const auto deadline=esp_timer_get_time()+12000000;
        if(esp_http_client_open(client,body.size())==ESP_OK && esp_http_client_write(client,body.data(),body.size())==int(body.size()) && esp_http_client_fetch_headers(client)>=0) {
            char buffer[512];bool good=true;
            while(true){int count=esp_http_client_read(client,buffer,sizeof(buffer));if(count<0 || esp_timer_get_time()>deadline){good=false;break;}if(!count)break;
                reply.append(buffer,count);if(reply.size()>32768){good=false;break;}}
            if(good && esp_http_client_is_complete_data_received(client))status=esp_http_client_get_status_code(client);
        }
        esp_http_client_close(client);esp_http_client_cleanup(client);if(status<0)reply.clear();return status;
    }
    uint32_t inactive_slot() override {
        auto running=esp_ota_get_running_partition();auto next=esp_ota_get_next_update_partition(nullptr);
        return running&&next&&next!=running&&slot_at(next->address)?next->address:0;
    }
    bool download(const std::string& path,const std::string& release,const ampve::OtaPolicy& policy,uint32_t address) override {
        error_="network";if(cancel_download.exchange(false)){error_="local_cancelled";return false;}auto slot=slot_at(address);
        if(!slot || address!=inactive_slot() || policy.app_size>slot->size){error_="image_rejected";return false;}
        auto client=http(path);if(!client)return false;
        std::string body="{\"release_id\":\""+release+"\"}";
        std::unique_ptr<unsigned char[]> buffer(new(std::nothrow) unsigned char[4096]);
        esp_ota_handle_t handle=0;bool begun=false,success=false;size_t total=0;
        crypto_hash_sha256_state hash;crypto_hash_sha256_init(&hash);
        const auto deadline=esp_timer_get_time()+180000000;
        if(buffer && esp_http_client_open(client,body.size())==ESP_OK && esp_http_client_write(client,body.data(),body.size())==int(body.size()) &&
           esp_http_client_fetch_headers(client)==int64_t(policy.app_size) && esp_http_client_get_status_code(client)==200) {
            // Buffer the complete image header/descriptor before erasing even the inactive slot.
            size_t prefix=0;constexpr size_t required=sizeof(esp_image_header_t)+sizeof(esp_image_segment_header_t)+sizeof(esp_app_desc_t);
            while(prefix<required && esp_timer_get_time()<deadline && !cancel_download){int count=esp_http_client_read(client,reinterpret_cast<char*>(buffer.get()+prefix),required-prefix);if(count<=0)break;prefix+=count;}
            const auto* image=reinterpret_cast<const esp_image_header_t*>(buffer.get());
            const auto* desc=reinterpret_cast<const esp_app_desc_t*>(buffer.get()+sizeof(esp_image_header_t)+sizeof(esp_image_segment_header_t));
            if(prefix==required && image->magic==ESP_IMAGE_HEADER_MAGIC && image->chip_id==ESP_CHIP_ID_ESP32P4 &&
               image->min_chip_rev_full<=103 && (!image->max_chip_rev_full || image->max_chip_rev_full>=103) && image->hash_appended &&
               desc->magic_word==ESP_APP_DESC_MAGIC_WORD && std::memchr(desc->version,0,sizeof(desc->version)) && policy.firmware_version==desc->version &&
               esp_ota_begin(slot,policy.app_size,&handle)==ESP_OK) {
                begun=true;
                while(true){
                    bool cancelled=cancel_download.exchange(false);
                    if(cancelled || esp_timer_get_time()>deadline){error_=cancelled?"local_cancelled":"network";break;}
                    size_t count=prefix;prefix=0;
                    if(!count){int received=esp_http_client_read(client,reinterpret_cast<char*>(buffer.get()),std::min(size_t(4096),policy.app_size-total));if(received<=0)break;count=received;}
                    if(total+count>policy.app_size || esp_ota_write(handle,buffer.get(),count)!=ESP_OK){error_="storage";break;}
                    crypto_hash_sha256_update(&hash,buffer.get(),count);total+=count;
                    if(!engine->progress(total))break;
                    if(total==policy.app_size){
                        unsigned char digest[32];char hex[65];crypto_hash_sha256_final(&hash,digest);sodium_bin2hex(hex,sizeof(hex),digest,sizeof(digest));
                        if(policy.app_sha256!=hex){error_="hash_mismatch";break;}
                        int extra=esp_http_client_read(client,reinterpret_cast<char*>(buffer.get()),1);
                        if(extra!=0 || !esp_http_client_is_complete_data_received(client))break;
                        success=esp_ota_end(handle)==ESP_OK;begun=false;if(!success)error_="image_rejected";break;
                    }
                }
            }else error_=cancel_download.exchange(false)?"local_cancelled":"image_rejected";
        }
        if(begun)esp_ota_abort(handle);
        esp_http_client_close(client);esp_http_client_cleanup(client);return success;
    }
    const char* failure() override {return error_;}
    bool verify_target(uint32_t address,const std::string& expected,size_t size) override {
        auto slot=slot_at(address);if(!slot || address!=inactive_slot() || size>slot->size)return false;
        esp_partition_pos_t position{slot->address,slot->size};esp_image_metadata_t metadata={};std::string hash;
        return esp_image_verify(ESP_IMAGE_VERIFY_SILENT,&position,&metadata)==ESP_OK && metadata.image_len==size && flash_hash(address,size,hash)&&hash==expected;
    }
    int select(uint32_t address,int64_t expires_at) override {
        error_="image_rejected";auto running=esp_ota_get_running_partition();auto slot=slot_at(address);
        if(!running || !slot || address!=inactive_slot())return -1;
        auto boot=esp_ota_get_boot_partition();if(boot!=running && boot!=slot)return -1;
        if(time(nullptr)>=expires_at || cancel_download.exchange(false)){
            error_=time(nullptr)>=expires_at?"approval_unavailable":"local_cancelled";
            return boot==running?0:-1;
        }
        esp_err_t result=esp_ota_set_boot_partition(slot);
        boot=esp_ota_get_boot_partition();
        if(boot==slot)return 1;
        if(result!=ESP_OK && boot==running)return 0;
        return -1;
    }

    bool target_failed(uint32_t address) override {auto slot=slot_at(address);esp_ota_img_states_t state;return slot && esp_ota_get_state_partition(slot,&state)==ESP_OK && (state==ESP_OTA_IMG_ABORTED||state==ESP_OTA_IMG_INVALID);}
    void restart() override {esp_restart();}
    void status(const char* message) override {ampve_ota_status(message);}
};
}
void ampve_cancel_update(){cancel_download=true;}
void ampve_ota_tick(const std::string& device,const std::string& credential,const std::string& running_hash) {
    if(AMPVE_BUILD_SEQUENCE==0)return; // No keys/sequence are provisioned in an ordinary development build.
    static NativePort port;static ampve::OtaClient client(port);
    port.token=credential;port.running_hash=running_hash;port.engine=&client;client.tick(device);
}
