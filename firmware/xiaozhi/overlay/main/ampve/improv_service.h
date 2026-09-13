#pragma once
#include "improv.h"
#include <array>
#include <string>
namespace ampve {
class ImprovPort {
public:
 virtual ~ImprovPort()=default;
 virtual int64_t now()=0;
 virtual int64_t authorized_until()=0;
 virtual bool connected(const std::string& ssid)=0;
 // 1 saved, 0 connection failed, -1 storage uncertain, -2 expired, -3 unavailable.
 virtual int configure(const std::string&,const std::string&,int64_t)=0;
 virtual void handoff()=0;
 virtual std::string version()=0;
 virtual void send(const uint8_t*,size_t)=0;
};
class ImprovService {
public:
 explicit ImprovService(ImprovPort& port):port_(port){}
 void feed(uint8_t byte);
 void tick();
private:
 ImprovPort& port_;
 std::array<uint8_t,265> frame_{};
 size_t size_=0;
 int64_t last_byte_=0,pending_until_=0;
 std::string pending_ssid_;
 improv::State announced_=improv::STATE_STOPPED;
 improv::State state();
 void packet(uint8_t,const std::vector<uint8_t>&);
 void error(improv::Error);
 void rpc(improv::Command,const std::vector<std::string>&);
 bool command(improv::ImprovCommand);
 bool safe_payload() const;
};
}
