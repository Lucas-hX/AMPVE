#include "box_audio_codec.h"
#include <iostream>

int main() {
    int normal_calls=0;
    for(int failure=0;failure<=normal_calls;++failure) {
        calls=allocations=rx_enabled=0;fail_at=failure;ampve_codec_failed=false;
        {
            BoxAudioCodec codec(nullptr,16000,16000,0,0,0,0,0,0,0,0,false);
            codec.EnableInput(true);
            std::vector<int16_t> tone(4000,20);
            assert(!codec.InputData(tone));
            codec.SetOutputVolume(10);codec.EnableOutput(true);codec.OutputData(tone);
            codec.EnableOutput(false);
            if(!failure) {assert(!ampve_codec_failed);normal_calls=calls;fail_at=calls+1;codec.EnableOutput(true);}
            else assert(ampve_codec_failed);
            assert(ampve_codec_failed);
            int allocated=allocations;
            codec.EnableOutput(true);codec.OutputData(tone);codec.SetOutputVolume(70);
            assert(allocations==allocated && live.empty() && rx_enabled==0);
        }
        assert(live.empty());
    }
    calls=0;fail_at=1;ampve_codec_failed=false;partial_channel_failure=true;
    {BoxAudioCodec codec(nullptr,16000,16000,0,0,0,0,0,0,0,0,false);assert(ampve_codec_failed && live.empty());}
    calls=0;fail_at=0;ampve_codec_failed=false;
    {BoxAudioCodec codec(nullptr,16000,24000,0,0,0,0,0,0,0,0,false);assert(ampve_codec_failed && calls==0 && live.empty());}
    calls=0;fail_at=0;ampve_codec_failed=false;
    {BoxAudioCodec codec(nullptr,16000,16000,0,0,0,0,0,0,0,0,false);assert(!ampve_codec_failed);}
    assert(live.empty() && rx_enabled==0);
    std::cout << normal_calls+4 << " audio failure/cleanup scenarios passed; no microphone capture\n";
}
