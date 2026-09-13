#pragma once
#include "ota_policy.h"
#include <string>

namespace ampve {
// Hardware/transport boundary. Implementations must keep credentials out of replies/logs.
class OtaPort {
public:
    virtual ~OtaPort() = default;
    virtual bool context(OtaContext&) = 0;
    virtual bool load(std::string&) = 0;
    virtual bool save(const std::string&) = 0;
    virtual bool advance_sequence(uint32_t) = 0;
    virtual int post(const std::string& path, const std::string& body, std::string& reply) = 0;
    virtual uint32_t inactive_slot() = 0;
    virtual bool download(const std::string& path, const std::string& release,
                          const OtaPolicy&, uint32_t slot) = 0;
    virtual const char* failure() { return "network"; }
    virtual bool verify_target(uint32_t slot, const std::string& hash, size_t size) = 0;
    // 1: selected; 0: previous boot selection verified; -1: outcome uncertain.
    virtual int select(uint32_t slot, int64_t expires_at) = 0;
    virtual bool target_failed(uint32_t slot) = 0;
    virtual void restart() = 0;
    virtual void status(const char*) = 0;
};
class OtaClient {
public:
    explicit OtaClient(OtaPort& port): port_(port) {}
    // Call only after local startup confirmation, from one worker, at a bounded interval.
    void tick(const std::string& device);
    // Called by download() after a durable write; false requires aborting the stream.
    bool progress(size_t bytes);
private:
    OtaPort& port_;
    bool initialized_ = false, interrupted_ = false, stopped_ = false;
    std::string device_, journal_;
    bool report(const char* state, size_t bytes, const char* error = "");
    bool flush();
    bool persist();
    bool approved(OtaPolicy& policy);
};
}
