#pragma once
#include "fake_esp.h"
#include <vector>
#define AUDIO_CODEC_DMA_DESC_NUM 6
#define AUDIO_CODEC_DMA_FRAME_NUM 240
// The inherited interface is simulated; BoxAudioCodec itself is the transformed upstream source.
class AudioCodec {
public:
 virtual ~AudioCodec() = default;
 virtual void SetOutputVolume(int n) { output_volume_=n; }
 virtual void EnableInput(bool n) { input_enabled_=n; }
 virtual void EnableOutput(bool n) { output_enabled_=n; }
 void OutputData(std::vector<int16_t>& data) { Write(data.data(),data.size()); }
 bool InputData(std::vector<int16_t>& data) { return Read(data.data(),data.size())>0; }
protected:
 i2s_chan_handle_t tx_handle_=nullptr,rx_handle_=nullptr;
 bool duplex_=false,input_reference_=false,input_enabled_=false,output_enabled_=false;
 int input_channels_=1,input_sample_rate_=0,output_sample_rate_=0,output_volume_=70;
 float input_gain_=0;
 virtual int Read(int16_t*,int)=0;
 virtual int Write(const int16_t*,int)=0;
};
