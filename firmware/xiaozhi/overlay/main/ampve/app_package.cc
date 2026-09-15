#include "app_package.h"
#include "cJSON.h"
#include "sodium.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <ctime>
#include <memory>
#include <set>
#include <vector>

namespace ampve {
namespace {
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
bool hex64(const std::string& text) {
    return text.size() == 64 && std::all_of(text.begin(), text.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    });
}
bool bounded(const std::string& raw, size_t max) {
    if (raw.empty() || raw.size() > max) return false;
    bool quoted = false, escaped = false; int depth = 0;
    for (unsigned char c : raw) {
        if (!c || c > 127) return false;
        if (quoted) { if (escaped) escaped = false; else if (c == '\\') escaped = true;
                      else if (c == '"') quoted = false; }
        else if (c == '"') quoted = true;
        else if (c == '{' || c == '[') { if (++depth > 4) return false; }
        else if (c == '}' || c == ']') { if (--depth < 0) return false; }
    }
    return !quoted && !depth;
}
bool sorted_unique(cJSON* node) {
    std::set<std::string> seen; std::string previous;
    for (auto item = node->child; item; item = item->next) {
        if (cJSON_IsObject(node)) {
            if (!item->string || !seen.insert(item->string).second ||
                (!previous.empty() && previous >= item->string)) return false;
            previous = item->string;
        }
        if (!sorted_unique(item)) return false;
    }
    return true;
}
Json parse(const std::string& raw, size_t max) {
    if (!bounded(raw, max)) return Json(nullptr, cJSON_Delete);
    const char* end = nullptr;
    Json root(cJSON_ParseWithLengthOpts(raw.c_str(), raw.size() + 1, &end, true), cJSON_Delete);
    if (!root || !sorted_unique(root.get())) root.reset();
    return root;
}
bool fields(cJSON* obj, std::initializer_list<const char*> names) {
    if (!cJSON_IsObject(obj) || static_cast<size_t>(cJSON_GetArraySize(obj)) != names.size()) return false;
    for (auto name : names) if (!cJSON_GetObjectItemCaseSensitive(obj, name)) return false;
    return true;
}
std::string str(cJSON* obj, const char* name) {
    auto item = cJSON_GetObjectItemCaseSensitive(obj, name);
    return cJSON_IsString(item) && item->valuestring ? item->valuestring : "";
}
bool integer(cJSON* obj, const char* name, uint32_t min, uint32_t max, uint32_t& out) {
    auto item = cJSON_GetObjectItemCaseSensitive(obj, name);
    if (!cJSON_IsNumber(item) || !std::isfinite(item->valuedouble) ||
        item->valuedouble < min || item->valuedouble > max ||
        std::floor(item->valuedouble) != item->valuedouble) return false;
    out = static_cast<uint32_t>(item->valuedouble); return true;
}
bool ascii_ui(const std::string& text, size_t max) {
    if (text.empty() || text.size() > max) return false;
    for (char c : text) if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
        (c >= '0' && c <= '9') || c == ' ' || c == '.' || c == ',' || c == ':' ||
        c == '!' || c == '?' || c == '_' || c == '+' || c == '-' || c == '/')) return false;
    return true;
}
bool identity_text(const std::string& text, size_t max, bool version = false) {
    if (text.empty() || text.size() > max) return false;
    if (version) {
        if (text.front() == '.' || text.back() == '.' ||
            std::count(text.begin(), text.end(), '.') != 2 || text.find("..") != std::string::npos)
            return false;
    } else if (!((text.front() >= '0' && text.front() <= '9') ||
                 (text.front() >= 'a' && text.front() <= 'z'))) return false;
    for (char c : text) if (!((c >= '0' && c <= '9') ||
        (version ? c == '.' : (c >= 'a' && c <= 'z') || c == '-'))) return false;
    return true;
}
bool decode(const std::string& raw, std::vector<unsigned char>& output, size_t maximum) {
    if (raw.empty() || raw.size() > 1400) return false;
    output.resize(maximum); size_t length = 0; const char* end = nullptr;
    if (sodium_base642bin(output.data(), output.size(), raw.c_str(), raw.size(), nullptr,
                          &length, &end, sodium_base64_VARIANT_ORIGINAL) != 0 ||
        end != raw.c_str() + raw.size()) return false;
    output.resize(length); return true;
}
int64_t expiry(const std::string& raw) {
    if (raw.size() != 20 || raw[4] != '-' || raw[7] != '-' || raw[10] != 'T' ||
        raw[13] != ':' || raw[16] != ':' || raw[19] != 'Z') return 0;
    int year, month, day, hour, minute, second;
    if (sscanf(raw.c_str(), "%4d-%2d-%2dT%2d:%2d:%2dZ",
               &year, &month, &day, &hour, &minute, &second) != 6 ||
        year < 2020 || year > 2100 || month < 1 || month > 12 || day < 1 ||
        day > 31 || hour > 23 || minute > 59 || second > 59) return 0;
    std::tm stamp{}; stamp.tm_year = year - 1900; stamp.tm_mon = month - 1;
    stamp.tm_mday = day; stamp.tm_hour = hour; stamp.tm_min = minute; stamp.tm_sec = second;
    const time_t result = timegm(&stamp);
    std::tm check{};
    if (result <= 0 || !gmtime_r(&result, &check) || check.tm_year != year - 1900 ||
        check.tm_mon != month - 1 || check.tm_mday != day || check.tm_hour != hour ||
        check.tm_min != minute || check.tm_sec != second) return 0;
    return result;
}
}

bool verify_app_package(const std::string& envelope, const std::string& expected_id,
                        const OtaContext& context, size_t psram_bytes, AppPackage& output) {
    output = {};
    if (!hex64(expected_id) || context.now_utc < 1700000000 ||
        context.publishers.empty() || context.publishers.size() > 16 || sodium_init() < 0) return false;
    auto outer = parse(envelope, 2048);
    if (!outer || !fields(outer.get(), {"payload", "signature"})) return false;
    std::vector<unsigned char> bytes, signature;
    if (!decode(str(outer.get(), "payload"), bytes, 1024) ||
        !decode(str(outer.get(), "signature"), signature, 64) || signature.size() != 64) return false;
    std::string payload(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    auto policy = parse(payload, 1024);
    if (!policy || !fields(policy.get(), {"schema", "api_version", "key_id", "name", "version", "kind",
        "profile_id", "profile_version", "layout_id", "chip_revision", "flash_bytes",
        "minimum_psram_bytes", "expires_at", "ui", "workflow"})) return false;
    char* printed = cJSON_PrintUnformatted(policy.get());
    const bool canonical = printed && payload == printed;
    cJSON_free(printed);
    if (!canonical) return false;
    uint32_t schema, api, profile_version, chip, flash, psram, duration;
    if (!integer(policy.get(), "schema", 1, 1, schema) ||
        !integer(policy.get(), "api_version", 1, 1, api) ||
        !integer(policy.get(), "profile_version", context.profile_version, context.profile_version, profile_version) ||
        !integer(policy.get(), "chip_revision", 103, 103, chip) ||
        !integer(policy.get(), "flash_bytes", context.flash_bytes, context.flash_bytes, flash) ||
        !integer(policy.get(), "minimum_psram_bytes", 33554432, 33554432, psram) ||
        psram_bytes < psram || str(policy.get(), "profile_id") != context.profile_id ||
        str(policy.get(), "layout_id") != context.layout_id) return false;
    const auto key_id = str(policy.get(), "key_id");
    auto publisher = std::find_if(context.publishers.begin(), context.publishers.end(),
        [&](const OtaPublisher& entry) { return entry.id == key_id && entry.development_ota && !entry.revoked; });
    if (publisher == context.publishers.end() || key_id.empty() || key_id.size() > 64) return false;
    unsigned char hash[crypto_hash_sha256_BYTES]; char hex[65];
    if (crypto_hash_sha256(hash, bytes.data(), bytes.size()) != 0) return false;
    sodium_bin2hex(hex, sizeof(hex), hash, sizeof(hash));
    if (expected_id != hex || std::find(context.revoked_releases.begin(),
        context.revoked_releases.end(), expected_id) != context.revoked_releases.end() ||
        crypto_sign_verify_detached(signature.data(), bytes.data(), bytes.size(),
            publisher->public_key) != 0) return false;
    AppPackage accepted;
    accepted.id = expected_id; accepted.name = str(policy.get(), "name");
    accepted.version = str(policy.get(), "version"); accepted.kind = str(policy.get(), "kind");
    if (!identity_text(accepted.name, 32) || !identity_text(accepted.version, 31, true) ||
        expiry(str(policy.get(), "expires_at")) <= context.now_utc) return false;
    auto ui = cJSON_GetObjectItemCaseSensitive(policy.get(), "ui");
    auto workflow = cJSON_GetObjectItemCaseSensitive(policy.get(), "workflow");
    if (!fields(ui, {"title", "body"}) || !fields(workflow, {"action", "duration_s", "start_muted"})) return false;
    accepted.title = str(ui, "title"); accepted.body = str(ui, "body");
    if (!ascii_ui(accepted.title, 48) || !ascii_ui(accepted.body, 96) ||
        !integer(workflow, "duration_s", 0, 3600, duration)) return false;
    auto start_muted = cJSON_GetObjectItemCaseSensitive(workflow, "start_muted");
    if (!cJSON_IsBool(start_muted)) return false;
    accepted.start_muted = cJSON_IsTrue(start_muted);
    const auto action = str(workflow, "action");
    if ((accepted.kind == "status" && action == "show_status" && duration == 0 && accepted.start_muted) ||
        (accepted.kind == "timer" && action == "local_timer" && duration >= 1 && accepted.start_muted) ||
        (accepted.kind == "companion" && action == "native_companion" && duration == 0)) {
        accepted.duration_s = duration; output = std::move(accepted); return true;
    }
    return false;
}
}
