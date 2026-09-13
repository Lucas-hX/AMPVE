// AMPVE native development shell. No cloud audio or firmware-write endpoint.
#include "runtime.h"
#include "image_identity.h"
#include "ota_platform.h"
#include "board.h"
#include "boards/waveshare/esp32-p4-wifi6-touch-lcd/config.h"
#include "profile.h"
#include "driver/gpio.h"
#include "wifi_board.h"
#include "audio_codec.h"
#include "ampve/boot_guard.h"
#include "wifi_manager.h"
#include "display.h"
#include "esp_lvgl_port.h"
#include "lvgl.h"
#include "esp_app_desc.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_heap_caps.h"
#include "esp_psram.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_ota_ops.h"
#include "esp_random.h"
#include "esp_sntp.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "cJSON.h"
#include "mbedtls/base64.h"
#include <algorithm>
#include <cmath>
#include <ctime>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

extern "C" {
extern const lv_image_dsc_t ampve_symbol;
extern const lv_image_dsc_t ampve_companion;
}
std::atomic<bool> ampve_wifi_initialized{false}, ampve_touch_ready{false}, ampve_codec_present{false}, ampve_codec_failed{false};
static std::atomic<bool> wifi_requested{false}, pair_requested{false}, tone_requested{false};
static std::atomic<bool> local_muted{true}, heard_tone{false}, tone_played{false};
static std::atomic<int> local_volume{-1};
static std::atomic<uint32_t> ui_ticks{0};
static std::atomic<bool> management_started{false}, boot_confirmed{false}, image_verified{false};
static std::mutex ui_mutex;
static std::string network_text="Starting Wi-Fi", management_text="Not paired", pair_code;
static std::string device_name="My AMPVE", about_text;
static std::atomic<bool> storage_ok{true};
static std::atomic<bool> codec_initialized{false};
static std::string setup_password;
extern "C" const char* ampve_wifi_password() { return setup_password.c_str(); }
static std::atomic<int> displayed_volume{40};
static lv_obj_t *body, *network_label, *status_label, *home_name=nullptr;
static int current_page=0;
static uint32_t flash_bytes=0;
static esp_chip_info_t chip;
static nvs_handle_t store_handle=0;


void ampve_request_wifi() { wifi_requested=true; }

static void message(const std::string& text) {
    std::lock_guard<std::mutex> lock(ui_mutex); management_text=text;
}
void ampve_ota_status(const char* text) { message(text); }
static std::string json_string(cJSON* value, const char* key, size_t maximum) {
    auto field=cJSON_GetObjectItemCaseSensitive(value,key);
    if (!cJSON_IsString(field) || !field->valuestring || strlen(field->valuestring)>maximum) return "";
    return field->valuestring;
}
static bool number(cJSON* object,const char* key,int minimum,int maximum,int& result) {
    auto item=cJSON_GetObjectItemCaseSensitive(object,key);
    if (!cJSON_IsNumber(item) || item->valuedouble<minimum || item->valuedouble>maximum ||
        item->valuedouble!=item->valueint) return false;
    result=item->valueint; return true;
}
static std::string encode(cJSON* object) {
    char* raw=cJSON_PrintUnformatted(object);
    std::string value=raw?raw:""; cJSON_free(raw); return value;
}
static bool save(const std::string& state) {
    if (!storage_ok || state.size()>1536 ||
        nvs_set_str(store_handle,"state",state.c_str())!=ESP_OK ||
        nvs_commit(store_handle)!=ESP_OK) {
        storage_ok=false; message("Storage error. Pairing paused; data preserved."); return false;
    }
    return true;
}
static std::string read_state() {
    size_t size=0;
    auto error=nvs_get_str(store_handle,"state",nullptr,&size);
    if (error==ESP_ERR_NVS_NOT_FOUND) return "{}";
    if (error!=ESP_OK || size>1536 || size<2) {storage_ok=false;return "";}
    std::string data(size,'\0');
    if (nvs_get_str(store_handle,"state",data.data(),&size)!=ESP_OK) {storage_ok=false;return "";}
    data.resize(size-1);return data;
}
static std::string credential() {
    // ESP32-P4 / IDF 6.1 keeps the SAR entropy source enabled at app startup.
    unsigned char raw[32], output[48]; size_t length=0;
    esp_fill_random(raw,sizeof(raw));
    if (mbedtls_base64_encode(output,sizeof(output),&length,raw,sizeof(raw))!=0) return "";
    std::string result(reinterpret_cast<char*>(output),length);
    for (auto& c:result) {if(c=='+')c='-';else if(c=='/')c='_';}
    while (!result.empty() && result.back()=='=') result.pop_back();
    return result;
}
static int post(const std::string& path,const std::string& token,cJSON* payload,std::string& reply) {
    const std::string url="https://ampve.com/api/devices/v1/"+path;
    const std::string request=encode(payload);
    if (request.empty() || request.size()>2048) return -1;
    esp_http_client_config_t config={};
    config.url=url.c_str();config.crt_bundle_attach=esp_crt_bundle_attach;
    config.timeout_ms=8000;config.disable_auto_redirect=true;config.buffer_size=1024;
    auto client=esp_http_client_init(&config);if(!client)return -1;
    esp_http_client_set_method(client,HTTP_METHOD_POST);
    esp_http_client_set_header(client,"Content-Type","application/json");
    const std::string auth="Bearer "+token;
    if(!token.empty())esp_http_client_set_header(client,"Authorization",auth.c_str());
    int status=-1;
    const auto deadline=esp_timer_get_time()+12000000;
    if(esp_http_client_open(client,request.size())==ESP_OK) {
        int sent=esp_http_client_write(client,request.data(),request.size());
        if(sent==static_cast<int>(request.size()) && esp_http_client_fetch_headers(client)>=0) {
            char buffer[256];bool valid=true;
            while(true) {
                if(esp_timer_get_time()>deadline){valid=false;break;}
                int count=esp_http_client_read(client,buffer,sizeof(buffer));
                if(count<0){valid=false;break;}
                if(count==0)break;
                reply.append(buffer,count);
                if(reply.size()>2048){valid=false;break;}
            }
            if(valid)status=esp_http_client_get_status_code(client);
        }
    }
    esp_http_client_close(client);esp_http_client_cleanup(client);
    if(status<0)reply.clear();
    return status;
}
static cJSON* hardware_report() {
    auto report=cJSON_CreateObject();
    cJSON_AddNumberToObject(report,"schema",2);
    auto compatibility=cJSON_AddObjectToObject(report,"compatibility");
    cJSON_AddStringToObject(compatibility,"profile_id",AMPVE_PROFILE_ID);
    cJSON_AddNumberToObject(compatibility,"profile_version",AMPVE_PROFILE_VERSION);
    cJSON_AddStringToObject(compatibility,"layout_id",AMPVE_LAYOUT_ID);
    cJSON_AddStringToObject(compatibility,"firmware_lineage",AMPVE_FIRMWARE_LINEAGE);
    if(flash_bytes)cJSON_AddNumberToObject(report,"flash_bytes",flash_bytes);
    else cJSON_AddNullToObject(report,"flash_bytes");
    cJSON_AddNumberToObject(report,"psram_bytes",esp_psram_get_size());
    auto screen=cJSON_AddObjectToObject(report,"display");
    cJSON_AddNumberToObject(screen,"width",1024);cJSON_AddNumberToObject(screen,"height",600);
    auto caps=cJSON_AddObjectToObject(report,"capabilities");
    cJSON_AddStringToObject(caps,"display","initialized");
    cJSON_AddStringToObject(caps,"touch",ampve_touch_ready?"initialized":"failed");
    cJSON_AddStringToObject(caps,"speaker",ampve_codec_failed?"failed":heard_tone?"passed":codec_initialized?"initialized":"configured");
    cJSON_AddStringToObject(caps,"microphone",ampve_codec_present?"configured":"unknown");
    cJSON_AddStringToObject(caps,"wifi",!ampve_wifi_initialized?"failed":WifiManager::GetInstance().IsConnected()?"passed":"initialized");
    return report;
}
static lv_obj_t* label(lv_obj_t* parent,const char* text,const lv_font_t* font=&lv_font_montserrat_20) {
    auto object=lv_label_create(parent);lv_label_set_text(object,text);
    lv_obj_set_style_text_font(object,font,0);lv_obj_set_style_text_color(object,lv_color_hex(0x252823),0);
    lv_obj_set_width(object,LV_PCT(100));lv_label_set_long_mode(object,LV_LABEL_LONG_WRAP);return object;
}
static void page(int id);
static lv_obj_t* button(lv_obj_t* parent,const char* text,lv_event_cb_t callback,intptr_t data=0) {
    auto item=lv_button_create(parent);lv_obj_set_height(item,64);lv_obj_set_width(item,LV_PCT(100));
    lv_obj_set_style_bg_color(item,lv_color_hex(0xE8ECDD),0);
    lv_obj_set_style_radius(item,14,0);lv_obj_set_style_shadow_width(item,0,0);
    auto caption=label(item,text);lv_obj_set_style_text_align(caption,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(caption);
    lv_obj_add_event_cb(item,callback,LV_EVENT_CLICKED,reinterpret_cast<void*>(data));return item;
}
static void go(lv_event_t* e) {page(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)));}
static void page(int id) {
    home_name=nullptr;
    current_page=id;lv_obj_clean(body);
    if(id==0) {
        auto symbol=lv_image_create(body);lv_image_set_src(symbol,&ampve_symbol);
        home_name=label(body,"Make yourself at home.",&lv_font_montserrat_36);
        auto row=lv_obj_create(body);lv_obj_set_size(row,LV_PCT(100),154);lv_obj_set_style_pad_all(row,6,0);
        lv_obj_set_flex_flow(row,LV_FLEX_FLOW_ROW);lv_obj_set_style_border_width(row,0,0);
        lv_obj_set_style_bg_opa(row,LV_OPA_TRANSP,0);
        auto companion=lv_obj_create(row);lv_obj_set_size(companion,320,140);
        lv_obj_set_style_bg_color(companion,lv_color_hex(0xE8ECDD),0);
        auto icon=lv_image_create(companion);lv_image_set_src(icon,&ampve_companion);
        lv_obj_align(icon,LV_ALIGN_LEFT_MID,0,0);
        auto title=label(companion,"Companion",&lv_font_montserrat_28);
        lv_obj_set_width(title,180);lv_obj_align(title,LV_ALIGN_RIGHT_MID,0,0);
        lv_obj_add_flag(companion,LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_event_cb(companion,go,LV_EVENT_CLICKED,reinterpret_cast<void*>(4));
        auto wifi=button(row,"Wi-Fi",go,1);lv_obj_set_size(wifi,245,140);
        auto info=button(row,"My device",go,2);lv_obj_set_size(info,245,140);
    } else if(id==1) {
        label(body,"Let's get connected.",&lv_font_montserrat_36);
        label(body,"Wi-Fi setup stays local. Your provider keys stay on AMPVE.");
        button(body,"Open local Wi-Fi setup",[](lv_event_t*){ampve_request_wifi();});
        auto& wifi=WifiManager::GetInstance();
        if(wifi.IsConfigMode()) {
            std::string hint="Connect your phone or PC to "+wifi.GetApSsid()+"\nPassword: "+setup_password+" | Open "+wifi.GetApWebUrl();
            label(body,hint.c_str());
        }
        button(body,"Pair with my AMPVE account",[](lv_event_t*){pair_requested=true;});
        std::lock_guard<std::mutex> lock(ui_mutex);
        if(!pair_code.empty())label(body,pair_code.c_str(),&lv_font_montserrat_36);
        else label(body,"A real pairing code appears here after you start pairing.");
    } else if(id==2) {
        label(body,"My device",&lv_font_montserrat_36);
        label(body,about_text.c_str());
        label(body,ampve_touch_ready?"Touch driver initialized":"Touch not initialized");
        label(body,ampve_codec_failed?"Audio unavailable. Navigation and recovery remain available.":heard_tone?"Speaker: you confirmed the test":ampve_codec_present?"Audio codecs responded; speaker test pending":"Audio codecs not confirmed");
        button(body,"Play a quiet speaker test",[](lv_event_t*){tone_requested=true;});
        if(tone_played && !ampve_codec_failed)button(body,"I heard the tone",[](lv_event_t*){if(tone_played && !ampve_codec_failed)heard_tone=true;page(2);});
    } else if(id==3) {
        label(body,"Comfort comes first.",&lv_font_montserrat_36);
        label(body,"Microphone capture is disabled in this first shell.");
        label(body,"Desired volume (0-80). Test tones always start quietly.");
        auto slider=lv_slider_create(body);lv_obj_set_size(slider,850,36);lv_slider_set_range(slider,0,80);
        lv_slider_set_value(slider,displayed_volume,LV_ANIM_OFF);
        lv_obj_add_event_cb(slider,[](lv_event_t* event) {
            local_volume=lv_slider_get_value(static_cast<lv_obj_t*>(lv_event_get_target(event)));
        },LV_EVENT_RELEASED,nullptr);
        button(body,"Wi-Fi and pairing",go,1);
        button(body,"Cancel firmware download",[](lv_event_t*){ampve_cancel_update();message("Cancellation requested before firmware restart.");});
    } else {
        label(body,"A little company.",&lv_font_montserrat_36);
        auto image=lv_image_create(body);lv_image_set_src(image,&ampve_companion);
        label(body,"Companion voice is coming next.\nThis shell never opens an AI session.");
    }
}
static void create_ui() {
    lvgl_port_lock(0);
    auto screen=lv_obj_create(nullptr);lv_obj_set_style_bg_color(screen,lv_color_hex(0xF7F5EE),0);
    lv_obj_set_flex_flow(screen,LV_FLEX_FLOW_COLUMN);lv_obj_set_style_pad_all(screen,20,0);
    auto header=lv_obj_create(screen);lv_obj_set_size(header,LV_PCT(100),52);
    lv_obj_set_flex_flow(header,LV_FLEX_FLOW_ROW);lv_obj_set_style_pad_all(header,8,0);
    auto brand=label(header,"AMPVE",&lv_font_montserrat_28);lv_obj_set_width(brand,180);
    network_label=label(header,"Starting Wi-Fi");lv_obj_set_flex_grow(network_label,1);
    body=lv_obj_create(screen);lv_obj_set_width(body,LV_PCT(100));lv_obj_set_flex_grow(body,1);
    lv_obj_set_style_bg_opa(body,LV_OPA_TRANSP,0);lv_obj_set_style_border_width(body,0,0);lv_obj_set_style_pad_all(body,8,0);
    lv_obj_set_flex_flow(body,LV_FLEX_FLOW_COLUMN);
    status_label=label(screen,"Not paired");lv_obj_set_height(status_label,26);
    auto nav=lv_obj_create(screen);lv_obj_set_size(nav,LV_PCT(100),84);
    lv_obj_set_flex_flow(nav,LV_FLEX_FLOW_ROW);lv_obj_set_style_pad_all(nav,8,0);
    for(int id: {0,3}){auto b=button(nav,id==0?"Home":"Settings",go,id);lv_obj_set_width(b,280);}
    auto mute=button(nav,"Microphone muted",[](lv_event_t*) {
        // Never enable capture from this shell. Remote settings cannot override local mute.
        local_muted=true;message("Microphone remains off in this shell.");
    });
    lv_obj_set_width(mute,350);
    lv_screen_load(screen);page(0);
    lv_timer_create([](lv_timer_t*) {
        ui_ticks++;
        std::lock_guard<std::mutex> lock(ui_mutex);
        lv_label_set_text(network_label,network_text.c_str());
        lv_label_set_text(status_label,management_text.c_str());
        if(home_name)lv_label_set_text(home_name,device_name.c_str());
    },500,nullptr);
    lvgl_port_unlock();
}
static void show_pair_page() {
    lvgl_port_lock(0);if(current_page==1)page(1);lvgl_port_unlock();
}
static bool identifier(const std::string& value, size_t size, bool uuid=false) {
    if(value.size()!=size)return false;
    for(size_t i=0;i<size;i++){
        char c=value[i];
        if(uuid){
            if(i==8 || i==13 || i==18 || i==23){if(c!='-')return false;}
            else if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;
        }else if(!((c>='0'&&c<='9')||(c>='a'&&c<='z')||(c>='A'&&c<='Z')||c=='-'||c=='_'))return false;
    }
    return true;
}
static void startup_check(void*) {
    vTaskDelay(pdMS_TO_TICKS(60000));
    bool healthy = ui_ticks>100 && ampve_wifi_initialized && ampve_touch_ready && storage_ok && management_started && image_verified;
    // Never advertise a confirmed startup after a failed otadata write.
    if(healthy && esp_ota_mark_app_valid_cancel_rollback()==ESP_OK &&
       ampve::reset_boot_attempts(store_handle)) {
        boot_confirmed=true;
    } else {
        printf("AMPVE startup diagnostics or confirmation failed. Attempting app rollback, otherwise bounded restart.\n");
        // This can only roll back if an earlier valid OTA app and compatible bootloader exist.
        esp_ota_mark_app_invalid_rollback_and_reboot();
        esp_restart();
    }
    vTaskDelete(nullptr);
}
static void worker(void*) {
    std::string running_hash; size_t running_size=0;
    image_verified=ampve::running_image_identity(running_hash,running_size);
    bool identity_reported=false;
    std::string stored=read_state();
    auto state=cJSON_Parse(stored.c_str());
    if(!state || !cJSON_IsObject(state)){storage_ok=false;message("Stored state is invalid. Data preserved.");}
    if(!state)state=cJSON_CreateObject();
    auto token=json_string(state,"credential",43);
    auto device=json_string(state,"device_id",36);
    if((!token.empty() && !identifier(token,43)) || (!device.empty() && (!identifier(device,36,true) || token.empty()))) {
        storage_ok=false;message("Stored identity invalid. Data preserved.");
    }
    {std::lock_guard<std::mutex> lock(ui_mutex);auto name=json_string(state,"name",80);if(!name.empty())device_name=name;}
    int ack=0,volume=40;
    number(state,"ack",0,1000000000,ack);number(state,"volume",0,80,volume);
    displayed_volume=volume;
    std::string enrollment=json_string(state,"enrollment",36),proof=json_string(state,"proof",43);
    int saved_expiry=0;number(state,"expiry",0,2147483647,saved_expiry);time_t expiry=saved_expiry;
    if(!enrollment.empty() && (!identifier(enrollment,36,true)||!identifier(proof,43)||token.empty()||!expiry)) {
        storage_ok=false;message("Stored enrollment invalid. Data preserved.");
    }
    {std::lock_guard<std::mutex> lock(ui_mutex);pair_code=json_string(state,"code",12);}
    int64_t ap_started=0;
    bool clock_started=false;int64_t next_request=0;
    management_started=true;
    while(true) {
        const auto now=esp_timer_get_time();
        if(wifi_requested.exchange(false)){
            static_cast<WifiBoard&>(Board::GetInstance()).EnterWifiConfigMode();
            show_pair_page();
        }
        auto& wifi=WifiManager::GetInstance();
        const bool connected=wifi.IsConnected();
        if(wifi.IsConfigMode()){
            if(!ap_started)ap_started=now;
            if(now-ap_started>300000000){wifi.StopConfigAp();wifi.StartStation();ap_started=0;message("Wi-Fi setup closed after five minutes. Open it locally to retry.");}
        }else ap_started=0;
        {std::lock_guard<std::mutex> lock(ui_mutex);
            network_text=!ampve_wifi_initialized?"Wi-Fi driver unavailable":connected?"Wi-Fi connected":wifi.IsConfigMode()?"Wi-Fi setup open":"Wi-Fi offline";}
        if(connected && !clock_started){
            esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
            esp_sntp_setservername(0,"pool.ntp.org");esp_sntp_init();clock_started=true;
        }
        if(tone_requested.exchange(false)){
            if(ampve_codec_failed){message("Audio unavailable. Restart the board before retrying diagnostics.");}
            else if(!ampve_codec_present){message("Audio codecs not confirmed. No tone played.");}
            else {
                auto codec=Board::GetInstance().GetAudioCodec();
                if(codec && !ampve_codec_failed){
                    codec_initialized=true;codec->EnableInput(false);codec->SetOutputVolume(10);codec->EnableOutput(true);
                    std::vector<int16_t> tone(codec->output_sample_rate()/4);
                    for(size_t i=0;i<tone.size();i++)tone[i]=static_cast<int16_t>(900*sin(2*3.14159265*440*i/codec->output_sample_rate()));
                    codec->OutputData(tone);codec->EnableOutput(false);codec->SetOutputVolume(volume);
                    tone_played=!ampve_codec_failed;
                    if(ampve_codec_failed){codec_initialized=false;heard_tone=false;message("Speaker test failed. Navigation and recovery remain available.");}
                    else message("Did you hear the tone? Confirm on My device.");
                    lvgl_port_lock(0);if(current_page==2)page(2);lvgl_port_unlock();
                }else message("Audio initialization failed. Navigation and recovery remain available.");
            }
        }
        int requested_volume=local_volume.exchange(-1);
        if(requested_volume>=0){
            cJSON_DeleteItemFromObject(state,"volume");cJSON_AddNumberToObject(state,"volume",requested_volume);
            if(save(encode(state))){volume=requested_volume;displayed_volume=volume;}
        }
        if(pair_requested.exchange(false)){
            if(!connected || time(nullptr)<1700000000 || !storage_ok) {
                message("Connect Wi-Fi and wait for secure time before pairing.");
            } else if(!enrollment.empty()) {
                message("Pairing already in progress. Use the displayed code.");
            } else if(!device.empty()) {
                message("Already paired. Revoke in the dashboard before pairing again.");
            } else {
                token=credential();ack=0;
                cJSON_DeleteItemFromObject(state,"ack");cJSON_AddNumberToObject(state,"ack",0);
                cJSON_DeleteItemFromObject(state,"credential");cJSON_AddStringToObject(state,"credential",token.c_str());
                if(save(encode(state))) {
                    auto payload=cJSON_CreateObject();cJSON_AddNumberToObject(payload,"protocol",1);
                    cJSON_AddStringToObject(payload,"hardware_profile",AMPVE_PROFILE_ID);
                    std::string reply;int status=post("enroll/","",payload,reply);cJSON_Delete(payload);
                    auto response=cJSON_Parse(reply.c_str());
                    if(status==201 && response) {
                        enrollment=json_string(response,"enrollment_id",36);proof=json_string(response,"bootstrap_proof",43);
                        auto code=json_string(response,"code",12);
                        if(identifier(enrollment,36,true) && identifier(proof,43) && code.size()==12){
                            expiry=time(nullptr)+600;
                            for(const char* key:{"enrollment","proof","code","expiry"})cJSON_DeleteItemFromObject(state,key);
                            cJSON_AddStringToObject(state,"enrollment",enrollment.c_str());cJSON_AddStringToObject(state,"proof",proof.c_str());
                            cJSON_AddStringToObject(state,"code",code.c_str());cJSON_AddNumberToObject(state,"expiry",expiry);
                            if(!save(encode(state))){cJSON_Delete(response);continue;}
                            {std::lock_guard<std::mutex> lock(ui_mutex);pair_code=code;}
                            message("Enter the code in ampve.com > Add a device.");show_pair_page();
                        }else{enrollment.clear();proof.clear();message("Pairing response invalid.");}
                    } else message("Pairing unavailable. Retry later.");
                    cJSON_Delete(response);
                }
            }
        }
        if(expiry && time(nullptr)>=expiry) {
            enrollment.clear();proof.clear();expiry=0;
            for(const char* key:{"enrollment","proof","code","expiry"})cJSON_DeleteItemFromObject(state,key);
            save(encode(state));
            {std::lock_guard<std::mutex> lock(ui_mutex);pair_code.clear();}
            message("Pairing expired. Start pairing again.");show_pair_page();
        }
        if(connected && storage_ok && time(nullptr)>1700000000 && now>=next_request) {
            next_request=now+30000000;
            if(!enrollment.empty()){
                auto payload=cJSON_CreateObject();cJSON_AddStringToObject(payload,"credential",token.c_str());
                std::string reply;int status=post("enroll/"+enrollment+"/exchange/",proof,payload,reply);cJSON_Delete(payload);
                auto response=cJSON_Parse(reply.c_str());
                if(status==200 && response){
                    auto received=json_string(response,"device_id",36);
                    if(identifier(received,36,true)){
                        cJSON_DeleteItemFromObject(state,"device_id");cJSON_AddStringToObject(state,"device_id",received.c_str());
                        for(const char* key:{"enrollment","proof","code","expiry"})cJSON_DeleteItemFromObject(state,key);
                        if(save(encode(state))){
                            device=received;identity_reported=false;enrollment.clear();proof.clear();expiry=0;
                            {std::lock_guard<std::mutex> lock(ui_mutex);pair_code.clear();}
                            message("Paired. Connecting to your dashboard.");show_pair_page();
                        }
                    }
                }
                cJSON_Delete(response);
                next_request=now+(status==429?60000000:5000000);
            } else if(!device.empty()){
                auto payload=cJSON_CreateObject();cJSON_AddNumberToObject(payload,"protocol",1);
                cJSON_AddStringToObject(payload,"firmware_version",esp_app_get_description()->version);
                std::string revision=std::to_string(chip.revision/100)+"."+std::to_string(chip.revision%100);
                cJSON_AddStringToObject(payload,"chip_revision",revision.c_str());
                cJSON_AddStringToObject(payload,"transport","wifi");cJSON_AddNumberToObject(payload,"acknowledged_version",ack);
                cJSON_AddItemToObject(payload,"hardware_report",hardware_report());
                std::string reply;int status=post(device+"/heartbeat/",token,payload,reply);cJSON_Delete(payload);
                auto response=cJSON_Parse(reply.c_str());
                if(status==200 && response){
                    auto config=cJSON_GetObjectItemCaseSensitive(response,"configuration");
                    int version=0,remote_volume=0;
                    auto mute=cJSON_GetObjectItemCaseSensitive(config,"microphone_muted");
                    auto name=json_string(config,"name",80);
                    if(number(config,"version",1,1000000000,version) && version>=ack &&
                        number(config,"volume",0,80,remote_volume) && cJSON_IsBool(mute) && !name.empty()){
                        if(version>ack && cJSON_IsTrue(mute)){
                            // Capture remains disabled even when the desired configuration says unmuted.
                            cJSON_DeleteItemFromObject(state,"ack");cJSON_AddNumberToObject(state,"ack",version);
                            cJSON_DeleteItemFromObject(state,"volume");cJSON_AddNumberToObject(state,"volume",remote_volume);
                            cJSON_DeleteItemFromObject(state,"name");cJSON_AddStringToObject(state,"name",name.c_str());
                            if(save(encode(state))){
                                ack=version;volume=remote_volume;displayed_volume=volume;
                                std::lock_guard<std::mutex> lock(ui_mutex);device_name=name;
                            }
                        }
                        message(cJSON_IsTrue(mute)?"Dashboard connected - microphone off":"Unmute requested; unsupported in this shell. Configuration pending.");
                    }else message("Invalid configuration. Previous settings kept.");
                } else if(status==401){
                    // Retain the credential until a physical user starts fresh pairing.
                    device.clear();identity_reported=false;cJSON_DeleteItemFromObject(state,"device_id");save(encode(state));
                    message("Device revoked. Start pairing locally to reconnect.");
                } else message("Dashboard unavailable. Local controls still work.");
                cJSON_Delete(response);
                if(status==200 && boot_confirmed && !identity_reported) {
                    auto identity=cJSON_CreateObject();cJSON_AddNumberToObject(identity,"protocol",1);
                    cJSON_AddStringToObject(identity,"app_sha256",running_hash.c_str());
                    cJSON_AddBoolToObject(identity,"boot_confirmed",true);
                    std::string identity_reply;
                    identity_reported=post(device+"/firmware/identity/",token,identity,identity_reply)==200;
                    cJSON_Delete(identity);
                }
                if(status==200 && boot_confirmed)ampve_ota_tick(device,token,running_hash);
                if(status==429)next_request=now+60000000;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(200));
    }
}
void ampve_runtime_start() {
    esp_chip_info(&chip);esp_flash_get_size(nullptr,&flash_bytes);
    if(chip.model!=CHIP_ESP32P4 || chip.revision<AMPVE_REVISION_MIN || chip.revision>AMPVE_REVISION_MAX || flash_bytes!=AMPVE_FLASH_BYTES) {
        printf("AMPVE recovery: chip/revision/flash do not match this development build.\n");return;
    }
    if(esp_psram_get_size()<AMPVE_MIN_PSRAM_BYTES) {
        printf("AMPVE recovery: initialized PSRAM is below the profile requirement. Nothing initialized or erased.\n");return;
    }
    // Refuse a legacy migration image/layout before opening NVS or starting drivers.
    for(const auto& expected:AMPVE_PARTITIONS) {
        const auto* partition=esp_partition_find_first(static_cast<esp_partition_type_t>(expected.type),
            static_cast<esp_partition_subtype_t>(expected.subtype),expected.name);
        if(!partition || partition->address!=expected.offset || partition->size!=expected.size || partition->encrypted) {
            printf("AMPVE recovery: partition layout differs from the versioned profile. Nothing initialized or erased.\n");return;
        }
    }
    const auto* running=esp_ota_get_running_partition();
    const auto* stock=esp_partition_find_first(ESP_PARTITION_TYPE_APP,ESP_PARTITION_SUBTYPE_APP_FACTORY,"factory");
    const auto* slot0=esp_partition_find_first(ESP_PARTITION_TYPE_APP,ESP_PARTITION_SUBTYPE_APP_OTA_0,"ota_0");
    const auto* slot1=esp_partition_find_first(ESP_PARTITION_TYPE_APP,ESP_PARTITION_SUBTYPE_APP_OTA_1,"ota_1");
    if(!running || !stock || !slot0 || !slot1 || stock->address!=AMPVE_FACTORY_OFFSET || stock->size!=AMPVE_FACTORY_SIZE ||
       slot0->address!=AMPVE_OTA_0_OFFSET || slot1->address!=AMPVE_OTA_1_OFFSET || slot0->size!=AMPVE_OTA_0_SIZE || slot1->size!=AMPVE_OTA_1_SIZE ||
       (running->address!=slot0->address && running->address!=slot1->address)) {
        printf("AMPVE recovery: stock partition layout required. Nothing initialized or erased.\n");return;
    }
    // NVS errors never trigger erase. Serial recovery is preferable to data destruction.
    if(nvs_flash_init()!=ESP_OK || nvs_open("ampve",NVS_READWRITE,&store_handle)!=ESP_OK){
        printf("AMPVE recovery: NVS unavailable; nothing erased. Use the audited USB recovery procedure.\n");return;
    }
    auto boot_attempt=ampve::record_boot_attempt(store_handle);
    if(boot_attempt==ampve::BootAttempt::StorageError){
        printf("AMPVE recovery: boot counter could not be read or committed. Data preserved; drivers not started.\n");return;
    }
    if(boot_attempt==ampve::BootAttempt::Recovery){
        printf("AMPVE recovery: repeated unconfirmed boots. Release BOOT, then hold it for five seconds to retry. Nothing erased.\n");
        // A local physical retry clears only this app's boot counter, never network/identity data.
        gpio_config_t input={};input.pin_bit_mask=1ULL<<BOOT_BUTTON_GPIO;input.mode=GPIO_MODE_INPUT;input.pull_up_en=GPIO_PULLUP_ENABLE;
        if(gpio_config(&input)!=ESP_OK){printf("AMPVE recovery: BOOT input unavailable. Use audited USB recovery.\n");return;}
        ampve::BootRetryHold retry;
        while(true){
            if(retry.update(gpio_get_level(BOOT_BUTTON_GPIO)==0,esp_timer_get_time())){
                if(ampve::reset_boot_attempts(store_handle))esp_restart();
                printf("AMPVE recovery: retry counter commit failed. Release BOOT before another five-second hold.\n");
            }
            vTaskDelay(pdMS_TO_TICKS(100));
        }
    }
    setup_password=credential().substr(0,16);
    if(xTaskCreate(startup_check,"ampve_startup",4096,nullptr,2,nullptr)!=pdPASS)return;
    auto& board=Board::GetInstance();
    if(!lv_display_get_default()){printf("AMPVE recovery: display not initialized.\n");return;}
    about_text="Waveshare P4 Touch LCD 7B\nAMPVE "+std::string(esp_app_get_description()->version)+
        " | ESP32-P4 revision 1.3\nFlash "+std::to_string(flash_bytes/(1024*1024))+" MiB | PSRAM "+
        std::to_string(esp_psram_get_size()/(1024*1024))+" MiB\nDisplay 1024 x 600 | microphone capture disabled";
    create_ui();
    board.StartNetwork();
    if(xTaskCreate(worker,"ampve_management",16384,nullptr,3,nullptr)!=pdPASS)
        message("Management task unavailable. Restart after reviewing diagnostics.");
}
