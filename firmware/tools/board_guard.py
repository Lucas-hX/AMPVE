"""Guard the pinned Waveshare display startup; retain the upstream integration diff."""
import subprocess
BOARD='main/boards/waveshare/esp32-p4-wifi6-touch-lcd/esp32-p4-wifi6-touch-lcd.cc'


def replace(source, old, new):
    if source.count(old)!=1:
        raise ValueError('Pinned board contract changed: '+old[:80])
    return source.replace(old,new)


def baseline(source):
    source=replace(source,'#include "codecs/box_audio_codec.h"\n','')
    source=replace(source,'#include "application.h"\n','')
    source=replace(source,'#include "display/lcd_display.h"\n','')
    for header in ('#include "esp_video.h"\n', '#include "esp_video_init.h"\n',
                   '#include "esp_cam_sensor_xclk.h"\n'):
        source=replace(source,header,'')
    source=replace(source,'#include "wifi_board.h"','#include "wifi_board.h"\n#include "ampve/runtime.h"')
    source=replace(source,'    LcdDisplay *display_;\n','')
    source=replace(source,'    EspVideo* camera_ = nullptr;\n','')
    camera_start=source.index('    void InitializeCamera() {')
    camera_end=source.index('    void InitializeButtons()',camera_start)
    source=source[:camera_start]+source[camera_end:]
    source=replace(source,'        InitializeCamera();\n','')
    a=source.index('        boot_button_.OnClick(');b=source.index('\n    }',a)
    source=source[:a]+'        boot_button_.OnClick([]() { ampve_request_wifi(); });'+source[b:]
    source=replace(source,'ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c(i2c_bus_, &tp_io_config, &tp_io_handle));',
        'if (esp_lcd_new_panel_io_i2c(i2c_bus_, &tp_io_config, &tp_io_handle) != ESP_OK) return;')
    source=replace(source,'ESP_ERROR_CHECK(esp_lcd_touch_new_i2c_gt911(tp_io_handle, &tp_cfg, &tp));',
        'if (esp_lcd_touch_new_i2c_gt911(tp_io_handle, &tp_cfg, &tp) != ESP_OK) return;')
    source=replace(source,'        lvgl_port_add_touch(&touch_cfg);','        ampve_touch_ready = lvgl_port_add_touch(&touch_cfg) != nullptr;')
    start=source.index('    virtual AudioCodec* GetAudioCodec() override {')
    end=source.index('\n    virtual Display *GetDisplay()',start)
    source=source[:start]+'    virtual AudioCodec* GetAudioCodec() override { return nullptr; }\n'+source[end:]
    source=replace(source,'''    virtual Display *GetDisplay() override {
        return display_;
    }''','''    virtual Display *GetDisplay() override { return nullptr; }''')
    source=replace(source,'''    virtual Camera* GetCamera() override {
        return camera_;
    }''','''    virtual Camera* GetCamera() override { return nullptr; }''')
    return source


def startup_transform(original):
    source=baseline(original)
    source=replace(source,'#include "ampve/runtime.h"','#include "ampve/runtime.h"\n#include <new>')
    source=replace(source,'    i2c_master_bus_handle_t i2c_bus_;','    i2c_master_bus_handle_t i2c_bus_ = nullptr;')
    source=replace(source,'    void InitializeCodecI2c() {','    bool InitializeCodecI2c() {')
    source=replace(source,'        ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_bus_cfg, &i2c_bus_));',
        '''        if (i2c_new_master_bus(&i2c_bus_cfg, &i2c_bus_) != ESP_OK || !i2c_bus_) {
            ESP_LOGE(TAG, "I2C startup failed; waiting for the boot supervisor"); return false;
        }
        return true;''')
    source=replace(source,'        esp_ldo_acquire_channel(&ldo_cfg, &phy_pwr_chan);',
        '''        auto result = esp_ldo_acquire_channel(&ldo_cfg, &phy_pwr_chan);
        if (result != ESP_OK) return result;
        if (!phy_pwr_chan) return ESP_FAIL;''')
    source=replace(source,'    void InitializeLCD() {','    bool InitializeLCD() {')
    source=replace(source,'        bsp_enable_dsi_phy_power();',
        '        if (bsp_enable_dsi_phy_power() != ESP_OK) { ESP_LOGE(TAG, "DSI power unavailable"); return false; }')
    calls=[('esp_lcd_new_dsi_bus(&bus_config, &mipi_dsi_bus)','mipi_dsi_bus'),
           ('esp_lcd_new_panel_io_dbi(mipi_dsi_bus, &dbi_config, &io)','io')]
    for name in ['st7703','st7701','hx8394','ek79007','jd9365','ili9881c']:
        call='esp_lcd_new_panel_'+name+'(io, &lcd_dev_config, &disp_panel)'
        # JD9365 appears in two alternate upstream board branches.
        if source.count(call+';')!=(2 if name=='jd9365' else 1):raise ValueError('Panel contract changed')
        source=source.replace(call+';', 'if ('+call+' != ESP_OK || !disp_panel) { ESP_LOGE(TAG, "LCD panel creation failed"); return false; }')
    for call,handle in calls:
        source=replace(source,call+';', 'if ('+call+' != ESP_OK || !'+handle+') { ESP_LOGE(TAG, "LCD transport creation failed"); return false; }')
    for call in ['esp_lcd_panel_reset(disp_panel)','esp_lcd_panel_init(disp_panel)']:
        source=replace(source,call+';', 'if ('+call+' != ESP_OK) { ESP_LOGE(TAG, "LCD initialization failed"); return false; }')
    source=replace(source,'display_ = new MipiLcdDisplay(', 'if (!ampve_initialize_display(')
    source=replace(source,'DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y, DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY);',
        '''DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y, DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY)) {
            ESP_LOGE(TAG, "LVGL display unavailable"); return false;
        }
        return true;''')
    source=replace(source,'        InitializeCodecI2c();\n        InitializeLCD();',
        '        if (!InitializeCodecI2c() || !InitializeLCD()) return;')
    source=replace(source,'        ESP_LOGI(TAG, "Touch panel initialized successfully");',
        '        if (ampve_touch_ready) ESP_LOGI(TAG, "Touch panel initialized successfully");\n        else ESP_LOGE(TAG, "Touch registration failed");')
    return source


def transform(original):
    source=startup_transform(original)
    source=replace(source,'''            .flags = {
                .swap_xy = 0,
                .mirror_x = 0,
                .mirror_y = 0,
            },''','''            .flags = {
                .swap_xy = 0,
#if defined(CONFIG_BOARD_TYPE_WAVESHARE_ESP32_P4_WIFI6_TOUCH_LCD_7B) && CONFIG_BOARD_TYPE_WAVESHARE_ESP32_P4_WIFI6_TOUCH_LCD_7B
                // The 7B GT911 coordinates are reversed on both axes relative to
                // the landscape display. Match the board-specific Waveshare BSP.
                .mirror_x = 1,
                .mirror_y = 1,
#else
                .mirror_x = 0,
                .mirror_y = 0,
#endif
            },''')
    return source


def prepare(work,pin):
    for path,transformer in [(BOARD,transform)]:
        original=subprocess.check_output(['git','-c','safe.directory='+str(work),'-C',str(work),
                                          'show',pin+':'+path]).decode()
        updated=transformer(original);target=work/path
        allowed=[original,updated]
        if path==BOARD:
            allowed.extend([baseline(original),startup_transform(original)])
        if target.read_text() not in allowed:raise ValueError('Refusing unrelated display changes: '+path)
        if target.read_text()!=updated:target.write_text(updated)
