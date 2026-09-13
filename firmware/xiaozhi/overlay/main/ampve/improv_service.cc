#include "improv_service.h"
#include <algorithm>
namespace ampve {
namespace { constexpr const char* kNext="https://ampve.com/devices/add/"; }
improv::State ImprovService::state(){
 if(pending_until_)return improv::STATE_PROVISIONING;
 if(port_.authorized_until()>port_.now())return improv::STATE_AUTHORIZED;
 return port_.connected("")?improv::STATE_PROVISIONED:improv::STATE_AWAITING_AUTHORIZATION;
}
void ImprovService::packet(uint8_t type,const std::vector<uint8_t>& data){
 if(data.size()>255)return;
 std::vector<uint8_t> result={'I','M','P','R','O','V',1,type,static_cast<uint8_t>(data.size())};
 result.insert(result.end(),data.begin(),data.end());uint8_t checksum=0;
 for(auto byte:result){checksum+=byte;}
 result.push_back(checksum);port_.send(result.data(),result.size());
}
void ImprovService::error(improv::Error value){packet(improv::TYPE_ERROR_STATE,{static_cast<uint8_t>(value)});}
void ImprovService::rpc(improv::Command command,const std::vector<std::string>& strings){
 size_t length=2;for(const auto& s:strings){if(s.size()>255)return;length+=s.size()+1;}
 if(length>255)return;
 auto data=improv::build_rpc_response(command,strings,false);data.pop_back();packet(improv::TYPE_RPC_RESPONSE,data);
}
void ImprovService::tick(){
 if(pending_until_){
  port_.handoff();
  if(port_.connected(pending_ssid_)){
   pending_until_=0;pending_ssid_.clear();
   announced_=improv::STATE_PROVISIONED;packet(improv::TYPE_CURRENT_STATE,{announced_});rpc(improv::WIFI_SETTINGS,{kNext});return;
  }
  if(port_.now()>=pending_until_){pending_until_=0;pending_ssid_.clear();error(improv::ERROR_UNABLE_TO_CONNECT);}
 }
 auto current=state();if(current!=announced_){announced_=current;packet(improv::TYPE_CURRENT_STATE,{current});}
}
bool ImprovService::safe_payload() const {
 // The pinned SDK assumes command/length bytes exist and reads password length
 // at ssid_end. Check exact bounds before invoking it, including its equality edge.
 if(frame_[7]!=improv::TYPE_RPC || frame_[8]<2)return false;
 const uint8_t* p=frame_.data()+9;size_t length=frame_[8];
 if(p[1]!=length-2)return false;
 if(p[0]!=improv::WIFI_SETTINGS)return length==2;
 if(length<4 || !p[2] || p[2]>32)return false;
 size_t end=3+p[2];if(end>=length || p[end]>64 || end+1+p[end]!=length)return false;
 for(size_t i=3;i<end;++i)if(!p[i])return false;
 for(size_t i=end+1;i<length;++i)if(!p[i])return false;
 return true;
}
void ImprovService::feed(uint8_t byte){
 auto now=port_.now();if(size_ && now-last_byte_>1000000){std::fill(frame_.begin(),frame_.end(),0);size_=0;}last_byte_=now;
 if(size_>=frame_.size()){size_=0;std::fill(frame_.begin(),frame_.end(),0);}
 frame_[size_]=byte;
 bool complete=size_>=9 && size_==static_cast<size_t>(frame_[8])+9;
 if(complete && !safe_payload()){error(improv::ERROR_INVALID_RPC);size_=0;std::fill(frame_.begin(),frame_.end(),0);return;}
 bool keep=improv::parse_improv_serial_byte(size_,byte,frame_.data(),
  [this](improv::ImprovCommand value){return command(std::move(value));},[this](improv::Error value){error(value);});
 if(!keep || complete){
  size_=0;std::fill(frame_.begin(),frame_.end(),0);
  if(!complete && byte=='I'){frame_[0]=byte;size_=1;}
 }
 else ++size_;
}
bool ImprovService::command(improv::ImprovCommand request){
 error(improv::ERROR_NONE);
 if(request.command==improv::GET_DEVICE_INFO){rpc(request.command,{"AMPVE",port_.version(),"waveshare-p4-7b","AMPVE Companion"});return false;}
 if(request.command==improv::GET_CURRENT_STATE){auto current=state();packet(improv::TYPE_CURRENT_STATE,{current});if(current==improv::STATE_PROVISIONED)rpc(request.command,{kNext});return false;}
 if(request.command!=improv::WIFI_SETTINGS){error(improv::ERROR_UNKNOWN_RPC);return false;}
 auto until=port_.authorized_until();
 if(until<=port_.now()){error(improv::ERROR_NOT_AUTHORIZED);return false;}
 if(pending_until_){error(improv::ERROR_UNKNOWN);return false;}
 packet(improv::TYPE_CURRENT_STATE,{improv::STATE_PROVISIONING});
 int result=port_.configure(request.ssid,request.password,until);
 std::fill(request.password.begin(),request.password.end(),'\0');
 if(result!=1){error(result==-2?improv::ERROR_NOT_AUTHORIZED:result==0?improv::ERROR_UNABLE_TO_CONNECT:improv::ERROR_UNKNOWN);announced_=improv::STATE_STOPPED;tick();return false;}
 pending_ssid_=std::move(request.ssid);pending_until_=port_.now()+60000000;announced_=improv::STATE_PROVISIONING;tick();return false;
}
}
