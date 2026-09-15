#include "app_runtime.h"
#include <utility>

namespace ampve {
bool AppRuntime::stage(const AppPackage& package) {
    if (package.id.empty() || package.version.empty() ||
        (package.kind != "status" && package.kind != "timer" && package.kind != "companion")) return false;
    if (package.id == active_.id) { staged_ = {}; return true; }
    staged_ = package; return true;
}
bool AppRuntime::activate(bool session_idle) {
    if (!session_idle || staged_.id.empty()) return false;
    previous_ = std::move(active_); active_ = std::move(staged_); staged_ = {};
    return true;
}
bool AppRuntime::rollback(bool session_idle) {
    if (!session_idle || previous_.id.empty()) return false;
    std::swap(active_, previous_); staged_ = {}; return true;
}
bool AppRuntime::disable(bool session_idle) {
    if (!session_idle) return false;
    staged_ = {}; previous_ = std::move(active_); active_ = {}; return true;
}
bool AppRuntime::revoke(const std::string& identity, bool session_idle) {
    if (identity.empty() || !session_idle) return false;
    bool changed = false;
    if (staged_.id == identity) { staged_ = {}; changed = true; }
    if (previous_.id == identity) { previous_ = {}; changed = true; }
    if (active_.id != identity) return changed;
    active_ = std::move(previous_); previous_ = {}; return true;
}
}
