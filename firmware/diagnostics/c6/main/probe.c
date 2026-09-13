// RAM-only development probe. No NVS, flash, Wi-Fi configuration or OTA calls.
#include <string.h>
#include <stdatomic.h>
#include <stdbool.h>
#include "driver/uart.h"
#include "esp_chip_info.h"
#include "esp_event.h"
#include "esp_hosted.h"
#include "esp_timer.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static char nonce[33];
static atomic_bool reported=false;
static void emit(const char *status, const esp_hosted_coprocessor_fwver_t *version, esp_err_t error) {
    if(atomic_exchange(&reported,true))return;
    esp_rom_printf("\n{\"kind\":\"ampve-c6-probe\",\"schema\":1,\"nonce\":\"%s\",\"status\":\"%s\",\"version\":[%u,%u,%u],\"error_code\":%d}\n",
        nonce,status,(unsigned)(version?version->major1:0),
        (unsigned)(version?version->minor1:0),(unsigned)(version?version->patch1:0),(int)error);
}
static void query(void *unused) {
    esp_hosted_coprocessor_fwver_t version={0};
    // Explicit initialization is idempotent; do not depend solely on a constructor.
    esp_err_t error=esp_hosted_init();
    if(error!=ESP_OK)emit("host_init_failed",NULL,error);
    else if((error=esp_hosted_connect_to_slave())!=ESP_OK)emit("connection_failed",NULL,error);
    else if((error=esp_hosted_get_coprocessor_fwversion(&version))!=ESP_OK)
        emit("version_query_failed",NULL,error);
    else if(version.major1==0 || version.major1>255 || version.minor1>255 || version.patch1>255)
        emit("invalid_version",NULL,ESP_ERR_INVALID_RESPONSE);
    else {
        uint32_t chip_id=0;char target[24]={0};
        error=esp_hosted_get_cp_info(&chip_id,target,sizeof(target)-1);
        if(error!=ESP_OK || strcmp(target,"esp32c6")!=0)
            emit("identity_unavailable",NULL,error==ESP_OK?ESP_ERR_INVALID_RESPONSE:error);
        else emit("observed",&version,ESP_OK);
    }
    vTaskSuspend(NULL);
}
void app_main(void) {
    esp_chip_info_t chip;esp_chip_info(&chip);
    if(chip.model!=CHIP_ESP32P4 || chip.revision!=103)return;
    // A fresh browser nonce prevents accidental acceptance of buffered old output.
    // It is correlation, not cryptographic hardware attestation.
    if(uart_driver_install(UART_NUM_0,256,0,0,NULL,0)!=ESP_OK)return;
    int used=0;int64_t until=esp_timer_get_time()+15000000;
    while(used<32 && esp_timer_get_time()<until){
        uint8_t c;
        if(uart_read_bytes(UART_NUM_0,&c,1,pdMS_TO_TICKS(100))!=1)continue;
        if((c>='0'&&c<='9')||(c>='a'&&c<='f'))nonce[used++]=(char)c;
        else used=0;
    }
    if(used!=32)return;
    esp_err_t event_error=esp_event_loop_create_default();
    if(event_error!=ESP_OK && event_error!=ESP_ERR_INVALID_STATE){emit("event_loop_failed",NULL,event_error);return;}
    if(xTaskCreate(query,"c6_query",4096,NULL,2,NULL)!=pdPASS){emit("task_start_failed",NULL,ESP_ERR_NO_MEM);return;}
    // The host library can block internally. A terminal timeout is never success.
    vTaskDelay(pdMS_TO_TICKS(20000));
    emit("timeout",NULL,ESP_ERR_TIMEOUT);
    vTaskSuspend(NULL);
}
