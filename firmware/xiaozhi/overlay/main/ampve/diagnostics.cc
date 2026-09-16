#include "diagnostics.h"
#include "cJSON.h"
#include "esp_app_desc.h"
#include "esp_heap_caps.h"
#include "esp_random.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <deque>
#include <mutex>
#include <utility>

namespace ampve {
namespace {
struct Event {
    unsigned sequence = 0;
    const char *kind = "operation", *operation = "idle", *error = "", *reset = "";
    std::string core_version, app_version;
    unsigned heap_free = 0, stack_min = 0;
};
std::mutex lock;
std::deque<Event> queue;
std::string boot_id, version;
unsigned next_sequence = 0;
CoreOperation last_operation = CoreOperation::Idle;
nvs_handle_t store = 0;
const char* operation_name(CoreOperation operation) {
    switch (operation) {
    case CoreOperation::CompanionStart: return "companion_start";
    case CoreOperation::CompanionCapture: return "companion_capture";
    case CoreOperation::CompanionStop: return "companion_stop";
    case CoreOperation::AppDownload: return "app_download";
    case CoreOperation::AppActivate: return "app_activate";
    case CoreOperation::AppRollback: return "app_rollback";
    case CoreOperation::CoreOta: return "core_ota";
    default: return "idle";
    }
}
const char* reset_name() {
    switch (esp_reset_reason()) {
    case ESP_RST_POWERON: return "power_on";
    case ESP_RST_SW: return "software";
    case ESP_RST_PANIC: return "panic";
    case ESP_RST_INT_WDT: case ESP_RST_TASK_WDT: case ESP_RST_WDT: return "watchdog";
    case ESP_RST_BROWNOUT: return "brownout";
    default: return "unknown";
    }
}
bool allowed_kind(const char* kind) {
    return kind && (!strcmp(kind,"boot") || !strcmp(kind,"operation") ||
                    !strcmp(kind,"error") || !strcmp(kind,"snapshot") || !strcmp(kind,"app"));
}
bool allowed_error(const char* code) {
    return code && (!*code || !strcmp(code,"audio_queue") || !strcmp(code,"audio_io") ||
        !strcmp(code,"network") || !strcmp(code,"package_rejected") ||
        !strcmp(code,"package_interrupted") || !strcmp(code,"package_revoked") ||
        !strcmp(code,"ota_journal") || !strcmp(code,"storage") || !strcmp(code,"unknown"));
}
void append(const char* kind, const char* error, const std::string& app, const char* reset = "") {
    if (boot_id.empty() || next_sequence > 65535 || queue.size() >= 16) return;
    Event event; event.sequence = next_sequence++; event.kind = kind;
    event.operation = operation_name(last_operation); event.error = error; event.reset = reset;
    event.core_version = version; event.app_version = app.size() <= 31 ? app : "";
    event.heap_free = std::min<size_t>(33554432, heap_caps_get_free_size(MALLOC_CAP_8BIT));
    event.stack_min = std::min<unsigned>(65536, uxTaskGetStackHighWaterMark(nullptr));
    queue.push_back(std::move(event));
}
}

void diagnostic_boot(const std::string& core_version) {
    std::lock_guard<std::mutex> guard(lock);
    if (!boot_id.empty()) return;
    char id[17]; snprintf(id,sizeof(id),"%08lx%08lx",
                           static_cast<unsigned long>(esp_random()),
                           static_cast<unsigned long>(esp_random()));
    boot_id = id; version = core_version.size() <= 31 ? core_version : "";
    if (nvs_open("ampve_diag", NVS_READWRITE, &store) == ESP_OK) {
        uint8_t prior = 0;
        if (nvs_get_u8(store,"last_op",&prior) == ESP_OK && prior <= 7)
            last_operation = static_cast<CoreOperation>(prior);
    }
    append("boot","","",reset_name());
    last_operation = CoreOperation::Idle;
    if (store) { nvs_set_u8(store,"last_op",0); nvs_commit(store); }
}
void diagnostic_operation(CoreOperation operation) {
    std::lock_guard<std::mutex> guard(lock);
    if (operation == last_operation) return;
    last_operation = operation;
    if (store && nvs_set_u8(store,"last_op",static_cast<uint8_t>(operation)) == ESP_OK)
        nvs_commit(store);
}
void diagnostic_event(const char* kind, const char* error_code, const std::string& app_version) {
    if (!allowed_kind(kind) || !allowed_error(error_code)) return;
    std::lock_guard<std::mutex> guard(lock);
    append(kind,error_code,app_version);
}
cJSON* diagnostic_batch(size_t maximum) {
    std::lock_guard<std::mutex> guard(lock);
    if (queue.empty() || !maximum) return nullptr;
    auto root = cJSON_CreateObject(); cJSON_AddNumberToObject(root,"protocol",1);
    auto list = cJSON_AddArrayToObject(root,"events");
    for (size_t i = 0; i < std::min<size_t>(maximum,queue.size()); ++i) {
        const auto& event = queue[i];
        auto item = cJSON_CreateObject();cJSON_AddItemToArray(list,item);
        cJSON_AddStringToObject(item,"boot_id",boot_id.c_str());
        cJSON_AddNumberToObject(item,"sequence",event.sequence);
        cJSON_AddStringToObject(item,"kind",event.kind);
        cJSON_AddStringToObject(item,"operation",event.operation);
        cJSON_AddStringToObject(item,"error_code",event.error);
        cJSON_AddStringToObject(item,"reset_reason",event.reset);
        cJSON_AddStringToObject(item,"core_version",event.core_version.c_str());
        cJSON_AddStringToObject(item,"app_version",event.app_version.c_str());
        cJSON_AddNumberToObject(item,"heap_free_bytes",event.heap_free);
        cJSON_AddNumberToObject(item,"stack_min_bytes",event.stack_min);
    }
    return root;
}
void diagnostic_ack(size_t count) {
    std::lock_guard<std::mutex> guard(lock);
    while (count-- && !queue.empty()) queue.pop_front();
}
}
