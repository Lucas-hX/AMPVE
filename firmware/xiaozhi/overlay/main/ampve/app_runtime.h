#pragma once
#include "app_package.h"
#include <string>

namespace ampve {
// RAM-only, one staged and one previous package. All transitions occur between sessions.
class AppRuntime {
public:
    bool stage(const AppPackage& package);
    bool activate(bool session_idle);
    bool rollback(bool session_idle);
    bool disable(bool session_idle);
    bool revoke(const std::string& identity, bool session_idle);
    const AppPackage& active() const { return active_; }
    const AppPackage& previous() const { return previous_; }
    const AppPackage& staged() const { return staged_; }
private:
    AppPackage active_, previous_, staged_;
};
}
