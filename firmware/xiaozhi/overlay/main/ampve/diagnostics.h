#pragma once
#include <cstddef>
#include <string>
struct cJSON;

namespace ampve {
enum class CoreOperation : unsigned char {
    Idle, CompanionStart, CompanionCapture, CompanionStop, AppDownload,
    AppActivate, AppRollback, CoreOta
};
void diagnostic_boot(const std::string& core_version);
void diagnostic_operation(CoreOperation operation);
void diagnostic_event(const char* kind, const char* error_code = "",
                      const std::string& app_version = "");
cJSON* diagnostic_batch(size_t maximum = 4);
void diagnostic_ack(size_t count);
}
