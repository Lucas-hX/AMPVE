#pragma once
#include <array>
#include <algorithm>
#include <cstddef>
// Read-only bounded request, multiplexed by the existing UART owner outside Improv frames.
namespace ampve {
class UsbStatusRequest {
 std::array<char,46> bytes_{};size_t used_=0;
public:
 void reset(){std::fill(bytes_.begin(),bytes_.end(),0);used_=0;}
 template<class Reply> void feed(char byte,Reply reply){
  constexpr char prefix[]="AMPVE_STATUS ";
  if(byte=='\n'){
   if(used_==45){bytes_[45]=0;reply(bytes_.data()+13);}
   reset();return;
  }
  if(used_>=45 || (used_<13?byte!=prefix[used_]:!((byte>='0'&&byte<='9')||(byte>='a'&&byte<='f')))){reset();return;}
  bytes_[used_++]=byte;
 }
};
}
