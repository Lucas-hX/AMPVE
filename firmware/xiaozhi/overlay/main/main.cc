#include "ampve/runtime.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_heap_caps.h"
#include "esp_rom_sys.h"
#include "esp_private/startup_internal.h"
#include "sdkconfig.h"

static_assert(CONFIG_ESP_MAIN_TASK_STACK_SIZE == 4096,
              "Keep the early main stack bounded; allocate the runtime stack after scheduler startup");

// Fixed numeric diagnostics only; no pointers, settings, identifiers or credentials.
static void report_heap(const char* phase) {
    constexpr uint32_t caps = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
    esp_rom_printf("AMPVE_BOOT_HEAP %s %u %u\n", phase,
                   static_cast<unsigned>(heap_caps_get_free_size(caps)),
                   static_cast<unsigned>(heap_caps_get_largest_free_block(caps)));
}

ESP_SYSTEM_INIT_FN(ampve_scheduler_heap, SECONDARY, BIT(0), 999) {
    report_heap("scheduler_pending");
    return ESP_OK;
}

static void runtime_task(void*) {
    ampve_runtime_start();
    vTaskDelete(nullptr);
}

extern "C" void app_main() {
    // IDF has reclaimed the ROM/startup-stack heaps before entering app_main.
    // The board/UI startup retains its original 16 KiB budget on the same core.
    report_heap("runtime_pending");
    if (xTaskCreatePinnedToCore(runtime_task, "ampve_runtime", 16384, nullptr, 1,
                               nullptr, CONFIG_ESP_MAIN_TASK_AFFINITY) != pdPASS) {
        esp_rom_printf("AMPVE runtime task allocation failed\n");
    }
}
