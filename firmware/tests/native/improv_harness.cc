#include "improv_service.h"
#include "usb_status.h"
#include <cassert>
#include <iostream>
struct Port:ampve::ImprovPort {
 int64_t time=1,until=0;int result=1,configured=0;std::string online;
 std::vector<std::vector<uint8_t>> messages;
 int64_t now()override{return time;}
 int64_t authorized_until()override{return until;}
 bool connected(const std::string& ssid)override{return !online.empty() && (ssid.empty() || online==ssid);}
 int configure(const std::string& ssid,const std::string& password,int64_t expiry)override{
  assert(ssid=="Fixture" && password=="fixture-password" && expiry==until);++configured;return result;
 }
 void handoff()override{}
 std::string version()override{return "0.1.10-improv-dev";}
 void send(const uint8_t* p,size_t n)override{
  assert(n>=10 && p[8]+10u==n);uint8_t checksum=0;for(size_t i=0;i<n-1;++i)checksum+=p[i];assert(checksum==p[n-1]);messages.emplace_back(p,p+n);
 }
 bool has(uint8_t type,uint8_t data){for(const auto& m:messages)if(m[7]==type && m[9]==data)return true;return false;}
};
void frame(ampve::ImprovService& service,std::vector<uint8_t> data,bool bad=false){
 std::vector<uint8_t> bytes={'I','M','P','R','O','V',1,3,static_cast<uint8_t>(data.size())};bytes.insert(bytes.end(),data.begin(),data.end());
 uint8_t sum=0;for(auto b:bytes)sum+=b;bytes.push_back(bad?sum+1:sum);for(auto b:bytes)service.feed(b);
}
std::vector<uint8_t> settings(){std::vector<uint8_t> out={1,25,7};for(char c:std::string("Fixture"))out.push_back(c);out.push_back(16);for(char c:std::string("fixture-password"))out.push_back(c);return out;}
int main(){
 int cases=0;
 {ampve::UsbStatusRequest status;int replies=0;std::string nonce(32,'a');
  auto reply=[&](const char* value){assert(value==nonce);++replies;};
  auto send=[&](const std::string& input){for(char byte:input)status.feed(byte,reply);};
  send("AMPVE_STATUS "+nonce+"\n");assert(replies==1);
  for(const auto& input:std::vector<std::string>{"AMPVE_STATUS short\n","AMPVE_STATUS "+nonce+"a\n","AMPVE_STATUS "+std::string(32,'Z')+"\n",std::string(10000,'x')+"\n"})send(input);
  assert(replies==1);send("AMPVE_STATUS "+nonce+"\n");assert(replies==2);++cases;
 }
 {Port port;ampve::ImprovService service(port);ampve::UsbStatusRequest status;int replies=0;
  // Even a complete status request inside a received Improv payload is private payload.
  std::string payload="AMPVE_STATUS "+std::string(32,'a')+"\n";
  std::vector<uint8_t> bytes={'I','M','P','R','O','V',1,3,static_cast<uint8_t>(payload.size())};
  bytes.insert(bytes.end(),payload.begin(),payload.end());uint8_t sum=0;for(auto b:bytes)sum+=b;bytes.push_back(sum);
  for(auto byte:bytes){if(service.receiving())status.reset();else status.feed(byte,[&](const char*){++replies;});service.feed(byte);}
  assert(replies==0);++cases;
 }

 {Port port;ampve::ImprovService service(port);service.feed('I');frame(service,{3,0});assert(port.has(4,3));++cases;}
 {Port port;ampve::ImprovService service(port);frame(service,{2,0});assert(port.has(1,1));frame(service,{3,0});assert(port.has(4,3));frame(service,settings());assert(port.configured==0 && port.has(2,4));++cases;}
 {Port port;port.until=300000001;ampve::ImprovService service(port);frame(service,settings());assert(port.configured==1 && port.has(1,3) && !port.has(4,1));port.online="Fixture";service.tick();assert(port.has(1,4) && port.has(4,1));++cases;}
 for(int result:{0,-1,-2,-3}){Port port;port.until=300000001;port.result=result;ampve::ImprovService service(port);frame(service,settings());assert(port.configured==1 && !port.has(4,1));assert(port.has(2,result==0?3:result==-2?4:255));++cases;}
 {Port port;port.until=300000001;ampve::ImprovService service(port);frame(service,settings());frame(service,settings());assert(port.configured==1);port.time+=60000000;service.tick();assert(port.has(2,3) && !port.has(4,1));++cases;}
 {Port port;port.until=1;ampve::ImprovService service(port);frame(service,settings());assert(port.configured==0 && port.has(2,4));++cases;}
 for(auto data:std::vector<std::vector<uint8_t>>{{},{1},{1,0},{1,1,0},{1,2,1,'x'},{1,3,1,'x',1},{1,2,0,0},{3,1,0}}){Port port;port.until=99;ampve::ImprovService service(port);frame(service,data);assert(port.configured==0 && port.has(2,1));frame(service,{3,0});assert(port.has(4,3));++cases;}
 {Port port;port.until=99;ampve::ImprovService service(port);frame(service,settings(),true);assert(port.configured==0 && port.has(2,1));++cases;}
 {Port port;ampve::ImprovService service(port);frame(service,{4,0});assert(port.has(2,2));++cases;}
 {Port port;port.until=99999999;ampve::ImprovService service(port);uint32_t seed=1;for(int i=0;i<20000;++i){seed=seed*1664525+1013904223;service.feed(seed>>24);}port.time+=2000000;frame(service,{3,0});assert(port.configured==0 && port.has(4,3));++cases;}
 std::cout<<cases<<" Improv scenarios passed with the pinned SDK and simulated transport/network\n";
}
