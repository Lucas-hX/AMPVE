#include "boot_guard.h"

namespace ampve {
BootAttempt record_boot_attempt(nvs_handle_t store) {
    uint32_t boots=0;
    auto result=nvs_get_u32(store,"boots",&boots);
    // Missing on first use is expected. Wrong types and read errors must preserve data.
    if (result!=ESP_OK && result!=ESP_ERR_NVS_NOT_FOUND) return BootAttempt::StorageError;
    if (result==ESP_ERR_NVS_NOT_FOUND) boots=0;
    if (boots>=3) return BootAttempt::Recovery;
    if (nvs_set_u32(store,"boots",boots+1)!=ESP_OK || nvs_commit(store)!=ESP_OK)
        return BootAttempt::StorageError;
    return BootAttempt::Ready;
}

bool reset_boot_attempts(nvs_handle_t store) {
    return nvs_set_u32(store,"boots",0)==ESP_OK && nvs_commit(store)==ESP_OK;
}
}
