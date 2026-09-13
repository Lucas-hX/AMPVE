#pragma once
#include <cassert>
#include <cstdint>
#include <new>
#include <atomic>
#define CONFIG_BOARD_TYPE_WAVESHARE_ESP32_P4_WIFI6_TOUCH_LCD_7B 1
#define MIPI_DSI_PHY_PWR_LDO_CHAN 3
#define MIPI_DSI_PHY_PWR_LDO_VOLTAGE_MV 2500
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_LVGL_PORT_INIT_CONFIG() {}
using esp_err_t=int;
using i2c_master_bus_handle_t=void*;using esp_ldo_channel_handle_t=void*;
using esp_lcd_panel_io_handle_t=void*;using esp_lcd_panel_handle_t=void*;using esp_lcd_dsi_bus_handle_t=void*;
constexpr int ESP_OK=0,ESP_FAIL=-1,I2C_NUM_1=1,AUDIO_CODEC_I2C_SDA_PIN=1,AUDIO_CODEC_I2C_SCL_PIN=2,I2C_CLK_SRC_DEFAULT=0;
constexpr int LCD_MIPI_DSI_LANE_BITRATE_MBPS=900,MIPI_DSI_DPI_CLK_SRC_DEFAULT=0,LCD_COLOR_FMT_RGB565=1,LCD_RGB_ELEMENT_ORDER_RGB=0,PIN_NUM_LCD_RST=33;
constexpr int DISPLAY_WIDTH=1024,DISPLAY_HEIGHT=600,DISPLAY_OFFSET_X=0,DISPLAY_OFFSET_Y=0;
constexpr bool DISPLAY_MIRROR_X=false,DISPLAY_MIRROR_Y=false,DISPLAY_SWAP_XY=false;
constexpr int AUDIO_CODEC_ES8311_ADDR=48,AUDIO_CODEC_ES7210_ADDR=64;
inline std::atomic<bool> ampve_touch_ready{false},ampve_codec_present{false};
inline int calls=0,fail_at=0,null_at=0,later_calls=0;
inline bool missing_default=false;
inline void* default_display=nullptr;
inline bool step(){return ++calls!=fail_at;}
inline int output(void** p){bool ok=step();*p=ok && calls!=null_at?reinterpret_cast<void*>(uintptr_t(1)):nullptr;return ok?0:-1;}
struct i2c_master_bus_config_t {int i2c_port,sda_io_num,scl_io_num,clk_source,glitch_ignore_cnt,intr_priority,trans_queue_depth;struct {bool enable_internal_pullup;} flags;};
struct esp_ldo_channel_config_t {int chan_id,voltage_mv;};
struct esp_lcd_dsi_bus_config_t {int bus_id,num_data_lanes,lane_bit_rate_mbps;};
struct esp_lcd_dbi_io_config_t {int virtual_channel,lcd_cmd_bits,lcd_param_bits;};
struct esp_lcd_dpi_panel_config_t {int dpi_clk_src,dpi_clock_freq_mhz,in_color_format,out_color_format,num_fbs;struct {int h_size,v_size,hsync_pulse_width,hsync_back_porch,hsync_front_porch,vsync_pulse_width,vsync_back_porch,vsync_front_porch;}video_timing;};
struct ek79007_vendor_config_t {struct {void* dsi_bus;esp_lcd_dpi_panel_config_t* dpi_config;}mipi_config;};
struct esp_lcd_panel_dev_config_t {int rgb_ele_order,bits_per_pixel,reset_gpio_num;const void* vendor_config;};
struct lvgl_port_cfg_t {};
struct lvgl_port_display_cfg_t {void* io_handle;void* panel_handle;void* control_handle;uint32_t buffer_size;bool double_buffer;uint32_t hres,vres;bool monochrome;struct {bool swap_xy,mirror_x,mirror_y;}rotation;struct {bool buff_dma,buff_spiram,sw_rotate;}flags;};
struct lvgl_port_display_dsi_cfg_t {struct {bool avoid_tearing;}flags;};
inline int i2c_new_master_bus(const i2c_master_bus_config_t*,void** p){return output(p);}
inline int esp_ldo_acquire_channel(const esp_ldo_channel_config_t*,void** p){return output(p);}
inline int esp_lcd_new_dsi_bus(const esp_lcd_dsi_bus_config_t*,void** p){return output(p);}
inline int esp_lcd_new_panel_io_dbi(void* bus,const esp_lcd_dbi_io_config_t*,void** p){assert(bus);return output(p);}
inline int esp_lcd_new_panel_ek79007(void* io,const esp_lcd_panel_dev_config_t*,void** p){assert(io);return output(p);}
inline int esp_lcd_panel_reset(void* p){assert(p);return step()?0:-1;}
inline int esp_lcd_panel_init(void* p){assert(p);return step()?0:-1;}
inline void lv_init(){}
inline int lvgl_port_init(const lvgl_port_cfg_t*){return step()?0:-1;}
inline void* lvgl_port_add_disp_dsi(const lvgl_port_display_cfg_t* cfg,const lvgl_port_display_dsi_cfg_t*){
 assert(cfg->panel_handle && cfg->io_handle);void* p=nullptr;output(&p);default_display=p;return p;
}
inline void* lv_display_get_default(){return missing_default?nullptr:default_display;}
inline void lv_display_set_offset(void* p,int,int){assert(p);}
// Theme, timer and base-display construction are separate, unvalidated boundaries here.
class LcdDisplay {
public:
 int width_,height_;void* display_=nullptr;
 LcdDisplay(void*,void*,int w,int h):width_(w),height_(h){}
 virtual ~LcdDisplay()=default;
};
class MipiLcdDisplay:public LcdDisplay {
public:
 MipiLcdDisplay(esp_lcd_panel_io_handle_t,esp_lcd_panel_handle_t,int,int,int,int,bool,bool,bool);
 static void* operator new(std::size_t n,const std::nothrow_t&) noexcept {if(!step())return nullptr;return ::operator new(n,std::nothrow);}
 static void operator delete(void* p) noexcept {::operator delete(p);}
 static void operator delete(void* p,const std::nothrow_t&) noexcept {::operator delete(p);}
};
