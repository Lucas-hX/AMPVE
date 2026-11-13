// AMPVE Core Lite: management, recovery and bounded application hosting only.
#include "runtime.h"
#include "image_identity.h"
#include "ota_platform.h"
#include "board.h"
#include "boards/waveshare/esp32-p4-wifi6-touch-lcd/config.h"
#include "profile.h"
#include "driver/gpio.h"
#include "wifi_board.h"
#include "ampve/boot_guard.h"
#include "ampve/app_package.h"
#include "ampve/app_runtime.h"
#include "ampve/diagnostics.h"
#include "ampve/improv_platform.h"
#include "ampve/publisher_trust.h"
#include "wifi_manager.h"
#include "esp_lvgl_port.h"
#include "esp_lcd_panel_ops.h"
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
#include "freertos/task.h"
#include <algorithm>
#include <ctime>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

extern "C" {
extern const lv_image_dsc_t ampve_symbol;
}

bool ampve_initialize_display(void* raw_io, void* raw_panel, int width, int height,
                              int offset_x, int offset_y, bool mirror_x,
                              bool mirror_y, bool swap_xy) {
    auto io = static_cast<esp_lcd_panel_io_handle_t>(raw_io);
    auto panel = static_cast<esp_lcd_panel_handle_t>(raw_panel);
    if (!io || !panel || width <= 0 || height <= 0) return false;
    const auto on = esp_lcd_panel_disp_on_off(panel, true);
    if (on != ESP_OK && on != ESP_ERR_NOT_SUPPORTED) return false;
    lv_init();
    lvgl_port_cfg_t port = ESP_LVGL_PORT_INIT_CONFIG();
    if (lvgl_port_init(&port) != ESP_OK) return false;
    const lvgl_port_display_cfg_t display = {
        .io_handle = io,
        .panel_handle = panel,
        .control_handle = nullptr,
        .buffer_size = static_cast<uint32_t>(width * 50),
        .double_buffer = false,
        .hres = static_cast<uint32_t>(width),
        .vres = static_cast<uint32_t>(height),
        .monochrome = false,
        .rotation = {.swap_xy = swap_xy, .mirror_x = mirror_x, .mirror_y = mirror_y},
        .flags = {.buff_dma = true, .buff_spiram = false, .sw_rotate = true},
    };
    const lvgl_port_display_dsi_cfg_t dsi = {.flags = {.avoid_tearing = false}};
    auto lv_display = lvgl_port_add_disp_dsi(&display, &dsi);
    if (!lv_display) return false;
    if (offset_x || offset_y) lv_display_set_offset(lv_display, offset_x, offset_y);
    return true;
}

std::atomic<bool> ampve_wifi_initialized{false}, ampve_touch_ready{false};
static std::atomic<bool> wifi_requested{false}, pair_requested{false};
static std::atomic<bool> platform_paired{false}, platform_online{false};
static std::atomic<uint32_t> ui_ticks{0};
static std::atomic<int64_t> app_timer_deadline{0};
static std::atomic<uint32_t> app_ui_revision{0};
static std::atomic<bool> management_started{false}, boot_confirmed{false}, image_verified{false}, usb_ready{false};
static std::mutex ui_mutex;
static std::string network_text="Starting Wi-Fi", management_text="Not paired", pair_code;
static std::string device_name="My AMPVE", about_text;
static std::atomic<bool> storage_ok{true};
static std::string setup_password, usb_image_hash;
static std::atomic<const char*> usb_phase{"starting"};
static std::atomic<bool> usb_display_ready{false};
extern "C" const char* ampve_wifi_password() { return setup_password.c_str(); }
static lv_obj_t *screen, *header, *body, *network_label, *platform_label, *header_name, *status_label, *nav;
static lv_obj_t *app_timer_label=nullptr;
static std::atomic<int> current_page{0};
static uint32_t flash_bytes=0;
static esp_chip_info_t chip;
static nvs_handle_t store_handle=0;
static ampve::AppRuntime live_app;
static std::mutex app_mutex;
static std::string last_admin_id, last_admin_result;
static std::mutex core_link_mutex;
static std::string core_link_device, core_link_token;
struct ReaderBook {
    std::string id, title;
    int pages = 0, progress = 1, revision = 0;
};
static std::mutex reader_mutex;
static std::vector<ReaderBook> reader_books;
static std::string reader_book_id, reader_book_title, reader_part, reader_text;
static int reader_page = 1, reader_pages = 0, reader_source_page = 0;
static std::atomic<int> reader_requested_page{0};
static std::atomic<bool> reader_progress_dirty{false};

static ampve::AppPackage active_app() {
    std::lock_guard<std::mutex> guard(app_mutex); return live_app.active();
}
static bool identifier(const std::string& value, size_t size, bool uuid);
static bool app_session_idle() {
    const auto deadline=app_timer_deadline.load();
    if(deadline && esp_timer_get_time()>=deadline)app_timer_deadline=0;
    return app_timer_deadline.load()==0;
}


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
static bool app_id(const std::string& value) {
    return value.size()==64 && std::all_of(value.begin(),value.end(),[](char c) {
        return (c>='0' && c<='9') || (c>='a' && c<='f');
    });
}
static void flush_diagnostics(const std::string& device,const std::string& token) {
    // Two measured events stay below the 2 KiB authenticated device API cap.
    auto payload=ampve::diagnostic_batch(2);if(!payload)return;
    const int count=cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(payload,"events"));
    std::string reply;const int status=post(device+"/diagnostics/events/",token,payload,reply);
    cJSON_Delete(payload);
    auto response=cJSON_Parse(reply.c_str());int accepted=0;
    if(status==200 && response && number(response,"accepted",count,count,accepted))
        ampve::diagnostic_ack(count);
    cJSON_Delete(response);
}
static void acknowledge_admin(const std::string& device,const std::string& token) {
    if(last_admin_id.empty() || last_admin_result.empty())return;
    auto report=cJSON_CreateObject();cJSON_AddNumberToObject(report,"protocol",1);
    cJSON_AddStringToObject(report,"result",last_admin_result.c_str());
    std::string reply;const int status=post(device+"/core/commands/"+last_admin_id+"/ack/",token,report,reply);
    cJSON_Delete(report);
    if(status==200){last_admin_id.clear();last_admin_result.clear();}
}
static void core_app_tick(const std::string& device,const std::string& token) {
    auto package=active_app();
    auto report=cJSON_CreateObject();cJSON_AddNumberToObject(report,"protocol",1);
    cJSON_AddNumberToObject(report,"api_version",1);
    cJSON_AddStringToObject(report,"core_version",esp_app_get_description()->version);
    cJSON_AddStringToObject(report,"active_id",package.id.c_str());
    cJSON_AddStringToObject(report,"app_version",package.version.c_str());
    cJSON_AddNumberToObject(report,"heap_free_bytes",
        std::min<size_t>(33554432,heap_caps_get_free_size(MALLOC_CAP_8BIT)));
    cJSON_AddNumberToObject(report,"stack_min_bytes",
        std::min<unsigned>(65536,uxTaskGetStackHighWaterMark(nullptr)));
    std::string reply;const int status=post(device+"/apps/sync/",token,report,reply);cJSON_Delete(report);
    if(status!=200)return;
    auto response=cJSON_Parse(reply.c_str());
    int protocol=0,api=0;
    if(!response || !cJSON_IsObject(response) ||
       !number(response,"protocol",1,1,protocol) ||
       !number(response,"api_version",1,1,api)) {
        cJSON_Delete(response);return;
    }
    const auto desired=json_string(response,"desired_id",64);
    auto disabled=cJSON_GetObjectItemCaseSensitive(response,"disabled");
    auto revoked_active=cJSON_GetObjectItemCaseSensitive(response,"revoked_active");
    if(!cJSON_IsBool(disabled) || (!desired.empty() && !app_id(desired))) {
        cJSON_Delete(response);return;
    }
    if(!cJSON_IsBool(revoked_active)) { cJSON_Delete(response);return; }
    if((cJSON_IsTrue(disabled) || cJSON_IsTrue(revoked_active)) && app_timer_deadline.load())
        app_timer_deadline=0;
    const auto revoked=cJSON_GetObjectItemCaseSensitive(response,"revoked_ids");
    if(cJSON_IsArray(revoked) && cJSON_GetArraySize(revoked)<=2) {
        for(auto item=revoked->child;item;item=item->next) {
            if(!cJSON_IsString(item) || !item->valuestring || !app_id(item->valuestring))continue;
            std::lock_guard<std::mutex> guard(app_mutex);
            if(live_app.revoke(item->valuestring,app_session_idle())) {
                ampve::diagnostic_event("error","package_revoked");app_ui_revision++;
            }
        }
    }
    bool failed=false,blocked=false;
    if(cJSON_IsTrue(disabled) || desired.empty()) {
        std::lock_guard<std::mutex> guard(app_mutex);
        if(!live_app.active().id.empty()) {
            if(live_app.disable(app_session_idle()))app_ui_revision++;
            else blocked=true;
        }
    } else {
        {
            std::lock_guard<std::mutex> guard(app_mutex);
            if(live_app.previous().id==desired && live_app.rollback(app_session_idle())) {
                ampve::diagnostic_operation(ampve::CoreOperation::AppRollback);
                ampve::diagnostic_event("app","",live_app.active().version);
                app_ui_revision++;
            }
        }
        bool need_download=false;
        {
            std::lock_guard<std::mutex> guard(app_mutex);
            need_download=live_app.active().id!=desired && live_app.staged().id!=desired &&
                live_app.previous().id!=desired;
        }
        if(need_download) {
            ampve::diagnostic_operation(ampve::CoreOperation::AppDownload);
            auto request=cJSON_CreateObject();cJSON_AddNumberToObject(request,"protocol",1);
            std::string envelope;const int download_status=post(device+"/apps/"+desired+"/package/",token,request,envelope);
            cJSON_Delete(request);
            ampve::OtaContext context; ampve_publisher_trust(context);
            context.now_utc=time(nullptr);context.profile_id=AMPVE_PROFILE_ID;
            context.profile_version=AMPVE_PROFILE_VERSION;context.layout_id=AMPVE_LAYOUT_ID;
            context.chip_revision=chip.revision;context.flash_bytes=flash_bytes;
            ampve::AppPackage candidate;
            if(download_status!=200 || !ampve::verify_app_package(envelope,desired,
                context,esp_psram_get_size(),candidate)) {
                failed=true;ampve::diagnostic_event("error",download_status==200?
                    "package_rejected":"package_interrupted");
            } else {
                std::lock_guard<std::mutex> guard(app_mutex);
                if(!live_app.stage(candidate))failed=true;
            }
        }
        if(!failed) {
            std::lock_guard<std::mutex> guard(app_mutex);
            if(live_app.staged().id==desired) {
                if(live_app.activate(app_session_idle())) {
                    ampve::diagnostic_operation(ampve::CoreOperation::AppActivate);
                    ampve::diagnostic_event("app","",live_app.active().version);
                    app_ui_revision++;
                } else blocked=true;
            } else if(live_app.active().id!=desired)blocked=true;
        }
    }
    const auto command=cJSON_GetObjectItemCaseSensitive(response,"command");
    if(cJSON_IsObject(command)) {
        const auto id=json_string(command,"id",36);
        const auto kind=json_string(command,"kind",20);
        if(identifier(id,36,true) && (kind=="assign_app" || kind=="kill_app" ||
            kind=="rollback_app" || kind=="snapshot")) {
            if(last_admin_id!=id) {
                last_admin_id=id;
                if(kind=="snapshot") {
                    ampve::diagnostic_event("snapshot","",active_app().version);
                    last_admin_result="applied";
                } else if(failed)last_admin_result="failed";
                else if(blocked)last_admin_result="blocked";
                else if(kind=="kill_app")last_admin_result=active_app().id.empty()?"applied":"blocked";
                else last_admin_result=active_app().id==desired?"applied":"blocked";
            }
            acknowledge_admin(device,token);
        }
    }
    cJSON_Delete(response);
}
static bool reader_report_progress(const std::string& device,const std::string& token,
                                   const std::string& book_id,int page) {
    auto request=cJSON_CreateObject();cJSON_AddNumberToObject(request,"protocol",1);
    cJSON_AddStringToObject(request,"book_id",book_id.c_str());cJSON_AddNumberToObject(request,"page",page);
    std::string reply;const int status=post(device+"/reader/progress/",token,request,reply);
    cJSON_Delete(request);return status==200;
}
static void reader_tick(const std::string& device,const std::string& token) {
    if(active_app().kind!="reader")return;
    auto request=cJSON_CreateObject();cJSON_AddNumberToObject(request,"protocol",1);
    std::string reply;const int status=post(device+"/reader/sync/",token,request,reply);
    cJSON_Delete(request);
    auto response=cJSON_Parse(reply.c_str());int protocol=0;
    auto books=response?cJSON_GetObjectItemCaseSensitive(response,"books"):nullptr;
    if(status!=200 || !response || !number(response,"protocol",1,1,protocol) ||
       !cJSON_IsArray(books) || cJSON_GetArraySize(books)>6){cJSON_Delete(response);return;}
    std::vector<ReaderBook> parsed;
    for(auto item=books->child;item;item=item->next){
        int pages=0,progress=0,revision=0;
        const auto id=json_string(item,"id",36),title=json_string(item,"title",64);
        if(!cJSON_IsObject(item) || !identifier(id,36,true) || title.empty() ||
           !number(item,"pages",1,100000,pages) || !number(item,"progress",1,pages,progress) ||
           !number(item,"revision",1,1000000000,revision)){cJSON_Delete(response);return;}
        parsed.push_back({id,title,pages,progress,revision});
    }
    cJSON_Delete(response);
    {
        std::lock_guard<std::mutex> guard(reader_mutex);
        reader_books=std::move(parsed);
        if(!reader_book_id.empty()){
            auto found=std::find_if(reader_books.begin(),reader_books.end(),[](const ReaderBook& book){
                return book.id==reader_book_id;
            });
            if(found==reader_books.end()){
                reader_book_id.clear();reader_book_title.clear();reader_text.clear();
                reader_page=1;reader_pages=0;reader_requested_page=0;app_ui_revision++;
            }
        }
    }
    std::string book_id;int current=1;int wanted=reader_requested_page.load();
    {
        std::lock_guard<std::mutex> guard(reader_mutex);book_id=reader_book_id;current=reader_page;
    }
    if(book_id.empty())return;
    if(wanted<1){
        if(reader_progress_dirty.exchange(false) &&
           !reader_report_progress(device,token,book_id,current))reader_progress_dirty=true;
        return;
    }
    request=cJSON_CreateObject();cJSON_AddNumberToObject(request,"protocol",1);
    cJSON_AddStringToObject(request,"book_id",book_id.c_str());cJSON_AddNumberToObject(request,"page",wanted);
    reply.clear();const int page_status=post(device+"/reader/page/",token,request,reply);cJSON_Delete(request);
    response=cJSON_Parse(reply.c_str());int page=0,pages_count=0,source_page=0;
    const auto returned_id=response?json_string(response,"book_id",36):"";
    const auto title=response?json_string(response,"title",64):"";
    const auto part=response?json_string(response,"part",48):"";
    const auto text=response?json_string(response,"text",1200):"";
    if(page_status!=200 || !response || returned_id!=book_id || title.empty() || part.empty() || text.empty() ||
       !number(response,"protocol",1,1,protocol) || !number(response,"page",1,100000,page) ||
       !number(response,"pages",page,100000,pages_count) ||
       !number(response,"source_page",1,100000,source_page)){
        cJSON_Delete(response);return;
    }
    cJSON_Delete(response);
    {
        std::lock_guard<std::mutex> guard(reader_mutex);
        if(reader_book_id!=book_id)return;
        reader_book_title=title;reader_part=part;reader_text=text;reader_page=page;
        reader_pages=pages_count;reader_source_page=source_page;reader_requested_page=0;
        reader_progress_dirty=true;app_ui_revision++;
    }
    if(reader_progress_dirty.exchange(false) &&
       !reader_report_progress(device,token,book_id,page))reader_progress_dirty=true;
}
static void core_network_task(void*) {
    unsigned cycle=0;
    while(true) {
        std::string device,token;
        {
            std::lock_guard<std::mutex> guard(core_link_mutex);
            device=core_link_device;token=core_link_token;
        }
        if(platform_online && boot_confirmed && !device.empty() && !token.empty()) {
            if(cycle%6==0){core_app_tick(device,token);flush_diagnostics(device,token);}
            reader_tick(device,token);
        }
        cycle++;vTaskDelay(pdMS_TO_TICKS(5000));
    }
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
    cJSON_AddStringToObject(caps,"speaker","unavailable");
    cJSON_AddStringToObject(caps,"microphone","unavailable");
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
static void reader_open(lv_event_t* e) {
    const auto index=static_cast<size_t>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)));
    std::lock_guard<std::mutex> guard(reader_mutex);
    if(index>=reader_books.size())return;
    const auto& book=reader_books[index];reader_book_id=book.id;reader_book_title=book.title;
    reader_page=book.progress;reader_pages=book.pages;reader_part.clear();reader_text.clear();
    reader_requested_page=book.progress;app_ui_revision++;
}
static void reader_turn(lv_event_t* e) {
    const int change=static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)));
    std::lock_guard<std::mutex> guard(reader_mutex);
    const int target=std::max(1,std::min(reader_pages,reader_page+change));
    if(!reader_book_id.empty() && target!=reader_page){
        reader_requested_page=target;reader_text.clear();app_ui_revision++;
    }
}
static void reader_shelf(lv_event_t*) {
    std::lock_guard<std::mutex> guard(reader_mutex);
    reader_book_id.clear();reader_book_title.clear();reader_part.clear();reader_text.clear();
    reader_page=1;reader_pages=0;reader_requested_page=0;app_ui_revision++;
}
static void page(int id) {
    app_timer_label=nullptr;
    current_page=id;
    lv_obj_set_style_pad_all(screen,20,0);
    for(auto chrome:{header,status_label,nav})lv_obj_remove_flag(chrome,LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_pad_all(body,8,0);
    lv_obj_set_style_bg_opa(body,LV_OPA_TRANSP,0);
    lv_obj_clean(body);
    if(id==0) {
        const auto package=active_app();
        auto row=lv_obj_create(body);lv_obj_set_size(row,LV_PCT(100),154);lv_obj_set_style_pad_all(row,6,0);
        lv_obj_set_flex_flow(row,LV_FLEX_FLOW_ROW);lv_obj_set_style_border_width(row,0,0);
        lv_obj_set_style_bg_opa(row,LV_OPA_TRANSP,0);
        const std::string app_title=package.id.empty()?"Apps":package.title;
        auto open=button(row,app_title.c_str(),go,4);lv_obj_set_size(open,320,140);
        auto wifi=button(row,"Wi-Fi",go,1);lv_obj_set_size(wifi,245,140);
        auto info=button(row,"My device",go,2);lv_obj_set_size(info,245,140);
        label(body,package.id.empty()?"No application is assigned. Choose one from ampve.com.":
              "The assigned application is active in the bounded AMPVE runtime.");
    } else if(id==1) {
        label(body,"Let's get connected.",&lv_font_montserrat_36);
        label(body,"Wi-Fi setup stays local. Device credentials remain protected by AMPVE Core.");
        button(body,"Open local Wi-Fi setup",[](lv_event_t*){ampve_request_wifi();});
        if(ampve_wifi_initialized && WifiManager::GetInstance().IsConfigMode()) {
            auto& wifi=WifiManager::GetInstance();
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
        label(body,"Audio and Companion are not included in this Core Lite build.");
    } else if(id==3) {
        label(body,"Core settings",&lv_font_montserrat_36);
        label(body,"Core keeps only connectivity, recovery, signed updates and the application host.");
        button(body,"Wi-Fi and pairing",go,1);
        button(body,"Cancel firmware download",[](lv_event_t*){ampve_cancel_update();message("Cancellation requested before firmware restart.");});
    } else {
        const auto package=active_app();
        bool reader_at_shelf=true;
        if(package.kind!="status" && package.kind!="timer" && package.kind!="reader") {
            label(body,"No portable application is active.");
        } else {
            label(body,package.title.c_str(),&lv_font_montserrat_36);
            label(body,package.body.c_str());
            if(package.kind=="status") {
                label(body,platform_online?"AMPVE platform connected":"AMPVE platform offline");
                label(body,ampve_wifi_initialized?"Wi-Fi driver ready":"Wi-Fi driver unavailable");
            } else if(package.kind=="timer") {
                app_timer_label=label(body,"Timer ready");
                auto start=button(body,"Start local timer",[](lv_event_t*) {
                    const auto current=active_app();
                    if(current.kind=="timer" && current.duration_s>=1 &&
                       !app_timer_deadline.load())
                        app_timer_deadline=esp_timer_get_time()+int64_t(current.duration_s)*1000000;
                });
                lv_obj_set_width(start,320);
                auto stop=button(body,"Stop local timer",[](lv_event_t*){app_timer_deadline=0;});
                lv_obj_set_width(stop,320);
            } else {
                std::lock_guard<std::mutex> guard(reader_mutex);
                reader_at_shelf=reader_book_id.empty();
                if(reader_book_id.empty()){
                    label(body,"Your shelf",&lv_font_montserrat_36);
                    label(body,reader_books.empty()?"No prepared books are selected in ampve.com.":
                          "Choose a book. Reading progress is synchronized with your private library.");
                    for(size_t index=0;index<reader_books.size();index++){
                        auto open=button(body,reader_books[index].title.c_str(),reader_open,index);
                        lv_obj_set_height(open,58);
                    }
                }else{
                    for(auto chrome:{header,status_label,nav})lv_obj_add_flag(chrome,LV_OBJ_FLAG_HIDDEN);
                    lv_obj_set_style_pad_all(screen,8,0);lv_obj_set_style_pad_all(body,10,0);
                    lv_obj_set_style_bg_color(body,lv_color_hex(0xF4EEDC),0);
                    lv_obj_set_style_bg_opa(body,LV_OPA_COVER,0);
                    auto top=lv_obj_create(body);lv_obj_set_size(top,LV_PCT(100),58);
                    lv_obj_set_flex_flow(top,LV_FLEX_FLOW_ROW);lv_obj_set_style_bg_opa(top,LV_OPA_TRANSP,0);
                    lv_obj_set_style_border_width(top,0,0);lv_obj_set_style_pad_all(top,2,0);
                    auto back=button(top,"Shelf",reader_shelf);lv_obj_set_size(back,120,52);
                    auto title=label(top,reader_book_title.c_str(),&lv_font_montserrat_20);lv_obj_set_flex_grow(title,1);
                    const std::string counter="Page "+std::to_string(reader_page)+" / "+std::to_string(reader_pages);
                    auto count=label(top,counter.c_str(),&lv_font_montserrat_20);lv_obj_set_width(count,180);
                    auto reading=label(body,reader_text.empty()?"Loading this page...":reader_text.c_str(),&lv_font_montserrat_20);
                    lv_obj_set_flex_grow(reading,1);lv_obj_set_style_text_line_space(reading,7,0);
                    auto source=label(body,(reader_part+" | PDF page "+std::to_string(reader_source_page)).c_str());
                    lv_obj_set_height(source,30);
                    auto controls=lv_obj_create(body);lv_obj_set_size(controls,LV_PCT(100),68);
                    lv_obj_set_flex_flow(controls,LV_FLEX_FLOW_ROW);lv_obj_set_style_bg_opa(controls,LV_OPA_TRANSP,0);
                    lv_obj_set_style_border_width(controls,0,0);lv_obj_set_style_pad_all(controls,2,0);
                    auto previous=button(controls,"Previous",reader_turn,-1);lv_obj_set_size(previous,220,60);
                    auto next=button(controls,"Next",reader_turn,1);lv_obj_set_size(next,220,60);
                }
            }
        }
        if(package.kind!="reader" || reader_at_shelf){
            auto home=button(body,"Home",go,0);lv_obj_set_width(home,220);
        }
    }
}
static void create_ui() {
    lvgl_port_lock(0);
    screen=lv_obj_create(nullptr);lv_obj_set_style_bg_color(screen,lv_color_hex(0xF7F5EE),0);
    lv_obj_set_flex_flow(screen,LV_FLEX_FLOW_COLUMN);lv_obj_set_style_pad_all(screen,20,0);
    header=lv_obj_create(screen);lv_obj_set_size(header,LV_PCT(100),52);
    lv_obj_set_flex_flow(header,LV_FLEX_FLOW_ROW);lv_obj_set_style_pad_all(header,8,0);
    auto symbol=lv_image_create(header);lv_image_set_src(symbol,&ampve_symbol);
    lv_obj_set_size(symbol,32,32);
    auto brand=label(header,"AMPVE",&lv_font_montserrat_20);lv_obj_set_width(brand,92);
    header_name=label(header,"My AMPVE",&lv_font_montserrat_20);
    lv_obj_set_width(header_name,206);lv_label_set_long_mode(header_name,LV_LABEL_LONG_DOT);
    network_label=label(header,"Starting Wi-Fi",&lv_font_montserrat_20);
    lv_obj_set_width(network_label,230);lv_label_set_long_mode(network_label,LV_LABEL_LONG_DOT);
    platform_label=label(header,"Not paired",&lv_font_montserrat_20);
    lv_obj_set_width(platform_label,172);
    body=lv_obj_create(screen);lv_obj_set_width(body,LV_PCT(100));lv_obj_set_flex_grow(body,1);
    lv_obj_set_style_bg_opa(body,LV_OPA_TRANSP,0);lv_obj_set_style_border_width(body,0,0);lv_obj_set_style_pad_all(body,8,0);
    lv_obj_set_flex_flow(body,LV_FLEX_FLOW_COLUMN);
    status_label=label(screen,"Not paired");lv_obj_set_height(status_label,26);
    nav=lv_obj_create(screen);lv_obj_set_size(nav,LV_PCT(100),84);
    lv_obj_set_flex_flow(nav,LV_FLEX_FLOW_ROW);lv_obj_set_style_pad_all(nav,8,0);
    for(int id: {0,3}){auto b=button(nav,id==0?"Home":"Settings",go,id);lv_obj_set_width(b,200);}
    lv_screen_load(screen);page(0);
    lv_timer_create([](lv_timer_t*) {
        ui_ticks++;
        {
            std::lock_guard<std::mutex> lock(ui_mutex);
            lv_label_set_text(network_label,network_text.c_str());
            lv_label_set_text(platform_label,!platform_paired?"Not paired":platform_online?"Paired":"Paired offline");
            lv_label_set_text(status_label,management_text.c_str());
            lv_label_set_text(header_name,device_name.c_str());
        }
        if(app_timer_label) {
            const auto deadline=app_timer_deadline.load();
            const auto remaining=deadline?std::max<int64_t>(0,(deadline-esp_timer_get_time()+999999)/1000000):0;
            if(deadline && !remaining)app_timer_deadline=0;
            const auto text=deadline?"Timer: "+std::to_string(remaining)+" seconds":"Timer ready";
            lv_label_set_text(app_timer_label,text.c_str());
        }
        static uint32_t shown_revision=0;
        if(shown_revision!=app_ui_revision.load()) {
            shown_revision=app_ui_revision.load();
            const int id=current_page.load();
            if(id==0 || id==4)page(id);
        }
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
#ifdef CONFIG_AMPVE_USB_COMMISSIONING
    // Initial USB commissioning confirms the management core, not peripherals/network.
    bool healthy = usb_ready && storage_ok && management_started && image_verified;
#else
    bool healthy = ui_ticks>100 && ampve_wifi_initialized && ampve_touch_ready && storage_ok && management_started && image_verified;
#endif
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
    ampve::diagnostic_boot(esp_app_get_description()->version);
    if(xTaskCreate(core_network_task,"ampve_core_net",12288,nullptr,2,nullptr)!=pdPASS)
        ampve::diagnostic_event("error","storage");
    std::string running_hash; size_t running_size=0;
    image_verified=ampve::running_image_identity(running_hash,running_size);
    {std::lock_guard<std::mutex> lock(ui_mutex);usb_image_hash=running_hash;}
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
    platform_paired=!device.empty() && identifier(device,36,true) && !token.empty();
    {
        std::lock_guard<std::mutex> guard(core_link_mutex);
        core_link_device=device;core_link_token=token;
    }
    {std::lock_guard<std::mutex> lock(ui_mutex);auto name=json_string(state,"name",80);if(!name.empty())device_name=name;}
    int ack=0;
    number(state,"ack",0,1000000000,ack);
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
        if(!ampve_wifi_initialized){
            platform_online=false;
            if(wifi_requested.exchange(false))message("Wi-Fi is not ready. Keep USB connected for setup.");
            {std::lock_guard<std::mutex> lock(ui_mutex);network_text="Wi-Fi pending · USB setup available";}
            vTaskDelay(pdMS_TO_TICKS(100));continue;
        }
        if(wifi_requested.exchange(false)){
            static_cast<WifiBoard&>(Board::GetInstance()).EnterWifiConfigMode();
            if(WifiManager::GetInstance().IsConfigMode())ap_started=now;
            ampve_improv_authorize();
            show_pair_page();
        }
        auto& wifi=WifiManager::GetInstance();
        const bool connected=wifi.IsConnected();
        if(!connected)platform_online=false;
        if(wifi.IsConfigMode()){
            if(!ap_started)ap_started=now;
            if(now-ap_started>300000000){wifi.StopConfigAp();wifi.StartStation();if(!wifi.IsConfigMode()){ap_started=0;message("Wi-Fi setup closed after five minutes. Open it locally to retry.");}}
        }else ap_started=0;
        {std::lock_guard<std::mutex> lock(ui_mutex);
            network_text=!ampve_wifi_initialized?"Wi-Fi initialization unavailable":connected?"Wi-Fi connected":wifi.IsConfigMode()?"Wi-Fi setup open":"Wi-Fi offline";}
        if(connected && !clock_started){
            esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
            esp_sntp_setservername(0,"pool.ntp.org");esp_sntp_init();clock_started=true;
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
                            platform_paired=true;platform_online=false;
                            {std::lock_guard<std::mutex> guard(core_link_mutex);
                             core_link_device=device;core_link_token=token;}
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
                platform_online=status==200 && response;
                if(status==200 && response){
                    auto config=cJSON_GetObjectItemCaseSensitive(response,"configuration");
                    int version=0;
                    auto name=json_string(config,"name",80);
                    if(number(config,"version",1,1000000000,version) && version>=ack && !name.empty()){
                        if(version>ack){
                            cJSON_DeleteItemFromObject(state,"ack");cJSON_AddNumberToObject(state,"ack",version);
                            cJSON_DeleteItemFromObject(state,"name");cJSON_AddStringToObject(state,"name",name.c_str());
                            if(save(encode(state))){
                                ack=version;
                                std::lock_guard<std::mutex> lock(ui_mutex);device_name=name;
                            }
                        }
                        message("Dashboard connected. Core is ready for application assignments.");
                    }else message("Invalid configuration. Previous settings kept.");
                } else if(status==401){
                    // Retain the credential until a physical user starts fresh pairing.
                    device.clear();identity_reported=false;cJSON_DeleteItemFromObject(state,"device_id");save(encode(state));
                    platform_paired=false;platform_online=false;
                    {std::lock_guard<std::mutex> guard(core_link_mutex);core_link_device.clear();}
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
static void start_network(void*) {
    usb_phase="network_starting";
    Board::GetInstance().StartNetwork();
    usb_phase=ampve_wifi_initialized?"network_initialized":"network_unavailable";
    if(!ampve_wifi_initialized)message("Wi-Fi initialization failed. USB setup remains available.");
    vTaskDelete(nullptr);
}
void ampve_runtime_start() {
    // UART ownership precedes all optional peripheral/network initialization.
    usb_ready=ampve_improv_start();
    usb_phase="checking_profile";
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
    usb_phase="opening_storage";
    // NVS errors never trigger erase. Serial recovery is preferable to data destruction.
    if(nvs_flash_init()!=ESP_OK || nvs_open("ampve",NVS_READWRITE,&store_handle)!=ESP_OK){
        printf("AMPVE recovery: NVS unavailable; nothing erased. Use the audited USB recovery procedure.\n");return;
    }
    usb_phase="checking_boot_counter";
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
    usb_phase="starting_core";
    setup_password=credential().substr(0,16);
    if(xTaskCreate(startup_check,"ampve_startup",4096,nullptr,2,nullptr)!=pdPASS)return;
    if(xTaskCreate(worker,"ampve_management",16384,nullptr,3,nullptr)!=pdPASS)return;
    usb_phase="starting_peripherals";
    Board::GetInstance();
    if(!lv_display_get_default()){printf("AMPVE recovery: display not initialized.\n");return;}
    about_text="Waveshare P4 Touch LCD 7B\nAMPVE "+std::string(esp_app_get_description()->version)+
        " | ESP32-P4 revision 1.3\nFlash "+std::to_string(flash_bytes/(1024*1024))+" MiB | PSRAM "+
        std::to_string(esp_psram_get_size()/(1024*1024))+" MiB\nDisplay 1024 x 600 | Core Lite application host";
    create_ui();usb_display_ready=true;
    if(!usb_ready)message("USB setup unavailable. Use the reviewed recovery route.");
    if(xTaskCreate(start_network,"ampve_network",8192,nullptr,2,nullptr)!=pdPASS)
        message("Wi-Fi task unavailable. USB setup remains available.");
}

std::string ampve_usb_status(const char* nonce) {
    auto data=cJSON_CreateObject();if(!data)return "";
    cJSON_AddStringToObject(data,"kind","ampve-usb-status");cJSON_AddNumberToObject(data,"schema",1);
    cJSON_AddStringToObject(data,"nonce",nonce);cJSON_AddStringToObject(data,"phase",usb_phase.load());
    cJSON_AddStringToObject(data,"firmware_version",esp_app_get_description()->version);
    {std::lock_guard<std::mutex> lock(ui_mutex);cJSON_AddStringToObject(data,"app_sha256",usb_image_hash.c_str());}
    cJSON_AddBoolToObject(data,"core_confirmed",boot_confirmed);
    cJSON_AddBoolToObject(data,"wifi_initialized",ampve_wifi_initialized);
    cJSON_AddBoolToObject(data,"display_ready",usb_display_ready);
    cJSON_AddBoolToObject(data,"touch_ready",ampve_touch_ready);
    auto raw=cJSON_PrintUnformatted(data);std::string result=raw?raw:"";cJSON_free(raw);cJSON_Delete(data);
    return result;
}
