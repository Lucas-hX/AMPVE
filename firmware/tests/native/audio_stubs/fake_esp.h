#pragma once
#include <cstdint>
#include <cassert>
#include <set>
#include <atomic>
#include <cstring>
inline std::atomic<bool> ampve_codec_failed{false};
inline bool partial_channel_failure=false;
inline int calls=0, fail_at=0, allocations=0, rx_enabled=0;
inline std::set<const void*> live;
inline bool step() { return ++calls!=fail_at; }
inline void* alloc() { if(!step())return nullptr; auto p=new int(++allocations);live.insert(p);return p; }
inline void free_resource(const void* p) { assert(p && live.erase(p)==1);delete static_cast<const int*>(p); }
using gpio_num_t=int;using i2c_port_t=int;using i2s_chan_handle_t=void*;
using audio_codec_data_if_t=void;using audio_codec_ctrl_if_t=void;using audio_codec_if_t=void;using audio_codec_gpio_if_t=void;using esp_codec_dev_handle_t=void*;
constexpr int ESP_OK=0,I2S_NUM_0=0,I2S_ROLE_MASTER=1,I2S_CLK_SRC_DEFAULT=0,I2S_MCLK_MULTIPLE_256=256,I2S_DATA_BIT_WIDTH_16BIT=16,I2S_SLOT_BIT_WIDTH_AUTO=0,I2S_SLOT_MODE_STEREO=2,I2S_STD_SLOT_BOTH=3,I2S_GPIO_UNUSED=-1,I2S_TDM_SLOT0=1,I2S_TDM_SLOT1=2,I2S_TDM_SLOT2=4,I2S_TDM_SLOT3=8,I2S_TDM_AUTO_WS_WIDTH=0,I2S_TDM_AUTO_SLOT_NUM=0;
constexpr int ESP_CODEC_DEV_WORK_MODE_DAC=1,ESP_CODEC_DEV_TYPE_OUT=1,ESP_CODEC_DEV_TYPE_IN=2,ES7210_SEL_MIC1=1,ES7210_SEL_MIC2=2,ES7210_SEL_MIC3=4,ES7210_SEL_MIC4=8;
using i2s_tdm_slot_mask_t=int;
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_CODEC_DEV_MAKE_CHANNEL_MASK(channel) (1 << (channel))
struct i2s_chan_config_t { int id,role,dma_desc_num,dma_frame_num;bool auto_clear_after_cb,auto_clear_before_cb;int intr_priority; };
struct Clock { uint32_t sample_rate_hz;int clk_src,ext_clk_freq_hz,mclk_multiple,bclk_div=0; };
struct Slot { int data_bit_width,slot_bit_width,slot_mode,slot_mask,ws_width;bool ws_pol,bit_shift,left_align,big_endian,bit_order_lsb,skip_mask=false;int total_slot=0; };
struct Pins { int mclk,bclk,ws,dout,din;struct {bool mclk_inv,bclk_inv,ws_inv;} invert_flags; };
struct i2s_std_config_t {Clock clk_cfg;Slot slot_cfg;Pins gpio_cfg;};
using i2s_tdm_config_t=i2s_std_config_t;
inline int i2s_new_channel(const i2s_chan_config_t*,void** tx,void** rx) {if(!step()){if(partial_channel_failure){*tx=new int(1);live.insert(*tx);allocations++;}return -1;}*tx=new int(1);*rx=new int(2);live.insert(*tx);live.insert(*rx);allocations+=2;return 0;}
inline int i2s_channel_init_std_mode(void*,const i2s_std_config_t*) { return step()?0:-1; }
inline int i2s_channel_init_tdm_mode(void*,const i2s_tdm_config_t*) { return step()?0:-1; }
inline int i2s_channel_enable(void* p) {if(*static_cast<int*>(p)==2)rx_enabled++;return step()?0:-1;}
inline int i2s_channel_disable(void* p) {if(p && *static_cast<int*>(p)==2 && rx_enabled)rx_enabled--;return 0;}
inline int i2s_del_channel(void* p) {free_resource(p);return 0;}
struct audio_codec_i2s_cfg_t {int port;void* rx_handle;void* tx_handle;};
struct audio_codec_i2c_cfg_t {int port,addr;void* bus_handle;};
struct es8311_codec_cfg_t {const void* ctrl_if;const void* gpio_if;int codec_mode;int pa_pin;bool use_mclk;struct {float pa_voltage,codec_dac_voltage;} hw_gain;};
struct es7210_codec_cfg_t {const void* ctrl_if;int mic_selected;};
struct esp_codec_dev_cfg_t {int dev_type;const void* codec_if;const void* data_if;};
struct esp_codec_dev_sample_info_t {int bits_per_sample,channel,channel_mask;uint32_t sample_rate;int mclk_multiple;};
inline const void* audio_codec_new_i2s_data(const audio_codec_i2s_cfg_t*){return alloc();}
inline const void* audio_codec_new_i2c_ctrl(const audio_codec_i2c_cfg_t*){return alloc();}
inline const void* audio_codec_new_gpio(){return alloc();}
inline const void* es8311_codec_new(const es8311_codec_cfg_t*){return alloc();}
inline const void* es7210_codec_new(const es7210_codec_cfg_t*){return alloc();}
inline void* esp_codec_dev_new(const esp_codec_dev_cfg_t*){return alloc();}
inline int esp_codec_dev_close(void*){return ampve_codec_failed?-1:step()?0:-1;}
inline void esp_codec_dev_delete(void* p){free_resource(p);}
inline void audio_codec_delete_codec_if(const void* p){free_resource(p);}
inline void audio_codec_delete_ctrl_if(const void* p){free_resource(p);}
inline void audio_codec_delete_gpio_if(const void* p){free_resource(p);}
inline void audio_codec_delete_data_if(const void* p){free_resource(p);}
inline int esp_codec_dev_set_out_vol(void*,int){return step()?0:-1;}
inline int esp_codec_dev_set_in_channel_gain(void*,int,float){return step()?0:-1;}
inline int esp_codec_dev_open(void*,const esp_codec_dev_sample_info_t*){return step()?0:-1;}
inline int esp_codec_dev_write(void*,void*,unsigned){return step()?0:-1;}
inline int esp_codec_dev_read(void*,void* data,unsigned size){if(!step())return -1;std::memset(data,0,size);return 0;}
