#include "box_audio_codec.h"
#include <iostream>

int main() {
    auto exercise=[](bool require_success) {
        int operational_calls=0;
        {
        BoxAudioCodec codec(nullptr,16000,16000,0,0,0,0,0,0,0,0,false);
        std::vector<int16_t> tone(4000,20);
        if(!ampve_codec_failed) codec.SetOutputVolume(10);
        // A local mute, ordinary stop and next Start must all reopen RX.
        for(int turn=0;turn<3 && !ampve_codec_failed;++turn) {
            codec.EnableInput(true);
            if(!ampve_codec_failed) {bool read=codec.InputData(tone);if(require_success)assert(read);}
            if(!ampve_codec_failed) codec.EnableOutput(true);
            if(!ampve_codec_failed) codec.OutputData(tone);
            if(!ampve_codec_failed) codec.EnableOutput(false);
            if(!ampve_codec_failed) codec.EnableInput(false);
            if(!ampve_codec_failed) codec.EnableInput(false); // idempotent second close
            if(require_success)assert(!ampve_codec_failed && rx_enabled==0);
        }
        if(require_success)assert(manual_rx_enable_calls==0 && manual_rx_disable_calls==0);
        operational_calls=calls;
        }
        return operational_calls;
    };
    calls=allocations=rx_enabled=manual_rx_enable_calls=manual_rx_disable_calls=0;fail_at=0;ampve_codec_failed=false;
    int normal_calls=0;
    {
        normal_calls=exercise(true);
        assert(!ampve_codec_failed && rx_enabled==0);
    }
    assert(live.empty());
    for(int failure=1;failure<=normal_calls;++failure) {
        calls=allocations=rx_enabled=manual_rx_enable_calls=manual_rx_disable_calls=0;fail_at=failure;ampve_codec_failed=false;
        {
            exercise(false);
            assert(ampve_codec_failed);
            int allocated=allocations;
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
    calls=allocations=rx_enabled=last_input_channel_mask=0;fail_at=0;ampve_codec_failed=false;
    {
        BoxAudioCodec codec(nullptr,16000,16000,0,0,0,0,0,0,0,0,true,30.0f,2,0.0f);
        codec.EnableInput(true);
        assert(!ampve_codec_failed && last_input_channel_mask==((1<<0) | (1<<2)));
        codec.EnableInput(false);
    }
    assert(live.empty() && rx_enabled==0);
    std::cout << normal_calls+4 << " audio failure/cleanup scenarios passed; microphone is locally gated\n";
}
