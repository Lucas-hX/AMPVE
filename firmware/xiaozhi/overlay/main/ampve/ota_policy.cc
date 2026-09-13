#include "ota_policy.h"
#include "cJSON.h"
#include "sodium.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <initializer_list>
#include <memory>
#include <set>

namespace ampve {
namespace {
constexpr size_t MAX_METADATA = 32768;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
bool hash(const std::string& s, size_t size = 64) {
    return s.size() == size && std::all_of(s.begin(), s.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    });
}
bool bounded_structure(const std::string& raw) {
    if (raw.empty() || raw.size() > MAX_METADATA || raw.find("\\u0000") != std::string::npos) return false;
    bool quoted = false, escaped = false;
    int depth = 0;
    for (unsigned char c : raw) {
        if (c == 0 || c > 127) return false; // Publisher canonical format is ASCII JSON.
        if (quoted) {
            if (escaped) escaped = false;
            else if (c == '\\') escaped = true;
            else if (c == '"') quoted = false;
        } else if (c == '"') quoted = true;
        else if (c == '{' || c == '[') { if (++depth > 8) return false; }
        else if (c == '}' || c == ']') { if (--depth < 0) return false; }
    }
    return !quoted && depth == 0;
}
bool unique_keys(cJSON* node) {
    std::set<std::string> seen;
    std::string previous;
    for (auto child = node->child; child; child = child->next) {
        if (cJSON_IsObject(node) && (!child->string || !seen.insert(child->string).second)) return false;
        if (cJSON_IsObject(node)) {
            if (!previous.empty() && previous >= child->string) return false;
            previous = child->string;
        }
        if (!unique_keys(child)) return false;
    }
    return true;
}
// cJSON emits UTF-8; the publisher's canonical JSON emits lowercase UTF-16 escapes.
// Convert only non-ASCII codepoints, retaining cJSON's standard escaping and number formatting.
bool canonical_json(cJSON* node, const std::string& expected) {
    char* printed = cJSON_PrintUnformatted(node);
    if (!printed) return false;
    std::string utf8(printed), ascii;
    cJSON_free(printed);
    const char* hex = "0123456789abcdef";
    auto escape = [&](uint32_t value) {
        ascii += "\\u";
        for (int shift = 12; shift >= 0; shift -= 4) ascii += hex[(value >> shift) & 15];
    };
    for (size_t i = 0; i < utf8.size();) {
        unsigned char c = utf8[i++];
        if (c < 128) { ascii += static_cast<char>(c); continue; }
        unsigned count = c >= 0xf0 ? 3 : c >= 0xe0 ? 2 : c >= 0xc2 ? 1 : 0;
        if (!count || c > 0xf4 || i + count > utf8.size()) return false;
        uint32_t point = c & ((1u << (6 - count)) - 1);
        for (unsigned n = 0; n < count; ++n) {
            unsigned char next = utf8[i++];
            if ((next & 0xc0) != 0x80) return false;
            point = (point << 6) | (next & 0x3f);
        }
        if (point > 0x10ffff || (point >= 0xd800 && point <= 0xdfff) ||
            point < (count == 1 ? 0x80u : count == 2 ? 0x800u : 0x10000u)) return false;
        if (point <= 0xffff) escape(point);
        else { point -= 0x10000; escape(0xd800 + (point >> 10)); escape(0xdc00 + (point & 1023)); }
    }
    return ascii == expected;
}
Json parse(const std::string& raw) {
    Json result(nullptr, cJSON_Delete);
    if (!bounded_structure(raw)) return result;
    const char* end = nullptr;
    result.reset(cJSON_ParseWithLengthOpts(raw.c_str(), raw.size() + 1, &end, true));
    if (!result || end != raw.c_str() + raw.size() || !unique_keys(result.get()) || !canonical_json(result.get(), raw)) result.reset();
    return result;
}
bool fields(cJSON* object, std::initializer_list<const char*> names) {
    if (!cJSON_IsObject(object) || static_cast<size_t>(cJSON_GetArraySize(object)) != names.size()) return false;
    for (auto name : names) if (!cJSON_GetObjectItemCaseSensitive(object, name)) return false;
    return true;
}
std::string str(cJSON* object, const char* name) {
    auto item = cJSON_GetObjectItemCaseSensitive(object, name);
    return cJSON_IsString(item) && item->valuestring ? item->valuestring : "";
}
bool integer(cJSON* object, const char* name, uint32_t minimum, uint32_t maximum, uint32_t& out) {
    auto item = cJSON_GetObjectItemCaseSensitive(object, name);
    if (!cJSON_IsNumber(item) || !std::isfinite(item->valuedouble) || item->valuedouble < minimum ||
        item->valuedouble > maximum || std::floor(item->valuedouble) != item->valuedouble) return false;
    out = static_cast<uint32_t>(item->valuedouble);
    return true;
}
bool equals(cJSON* object, const char* name, uint32_t expected) {
    uint32_t value = 0;
    return integer(object, name, expected, expected, value);
}
bool review(cJSON* object, const char* name) {
    auto value = str(object, name);
    return !value.empty() && value.size() <= 1000 && value.find("REPLACE") == std::string::npos &&
        value.find_first_not_of(" \t\r\n") != std::string::npos;
}
bool decode(const std::string& encoded, std::vector<unsigned char>& bytes, size_t maximum) {
    if (encoded.empty() || encoded.size() > MAX_METADATA) return false;
    bytes.resize(maximum);
    size_t length = 0;
    const char* end = nullptr;
    if (sodium_base642bin(bytes.data(), bytes.size(), encoded.c_str(), encoded.size(), nullptr,
                         &length, &end, sodium_base64_VARIANT_ORIGINAL) != 0 || end != encoded.c_str() + encoded.size()) return false;
    bytes.resize(length);
    return true;
}
std::string sha(const unsigned char* data, size_t size) {
    unsigned char digest[crypto_hash_sha256_BYTES];
    char hex[65];
    if (crypto_hash_sha256(digest, data, size) != 0) return "";
    sodium_bin2hex(hex, sizeof(hex), digest, sizeof(digest));
    return hex;
}
int64_t expiry(const std::string& value) {
    if (value.size() != 20 || value[4] != '-' || value[7] != '-' || value[10] != 'T' ||
        value[13] != ':' || value[16] != ':' || value[19] != 'Z') return 0;
    for (size_t i = 0; i < value.size(); ++i) {
        if (i == 4 || i == 7 || i == 10 || i == 13 || i == 16 || i == 19) continue;
        if (value[i] < '0' || value[i] > '9') return 0;
    }
    auto number = [&](size_t start, size_t length) {
        int out = 0;
        for (size_t i = start; i < start + length; ++i) out = out * 10 + value[i] - '0';
        return out;
    };
    auto leap = [](int y) { return y % 4 == 0 && (y % 100 != 0 || y % 400 == 0); };
    int y = number(0,4), m = number(5,2), d = number(8,2);
    int h = number(11,2), minute = number(14,2), second = number(17,2);
    if (y < 1970 || m < 1 || m > 12 || h > 23 || minute > 59 || second > 59) return 0;
    int months[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    if (leap(y)) months[1] = 29;
    if (d < 1 || d > months[m-1]) return 0;
    int64_t days = d - 1;
    for (int year = 1970; year < y; ++year) days += leap(year) ? 366 : 365;
    for (int month = 1; month < m; ++month) days += months[month-1];
    return ((days * 24 + h) * 60 + minute) * 60 + second;
}
}

bool verify_ota_policy(const std::string& envelope_json, const std::string& expected_release_id,
                       const OtaContext& ctx, OtaPolicy& output) {
    output = {};
    if (sodium_init() < 0 || !hash(expected_release_id) || ctx.publishers.empty() || ctx.publishers.size() > 16 ||
        ctx.minimum_sequence == 0 || ctx.confirmed_sequence == 0 || ctx.now_utc < 1700000000 ||
        !hash(ctx.running_app_sha256) || !hash(ctx.bootloader_sha256) || !hash(ctx.table_sha256)) return false;
    auto envelope = parse(envelope_json);
    if (!envelope || !fields(envelope.get(), {"payload","signature"})) return false;
    std::vector<unsigned char> payload, signature;
    if (!decode(str(envelope.get(),"payload"), payload, MAX_METADATA) ||
        !decode(str(envelope.get(),"signature"), signature, crypto_sign_BYTES) || signature.size() != crypto_sign_BYTES) return false;
    auto identity = sha(payload.data(), payload.size());
    if (identity != expected_release_id || std::find(ctx.revoked_releases.begin(), ctx.revoked_releases.end(), identity) != ctx.revoked_releases.end()) return false;
    auto parsed = parse(std::string(payload.begin(), payload.end()));
    auto policy = parsed.get();
    if (!policy || !fields(policy, {"schema","key_id","sequence","channel","purpose","installable","profile","compatibility",
        "chip_revision","flash_bytes","expires_at","repository_commit","firmware_version","app","bootloader_sha256",
        "table_sha256","bootloader_review","c6_review","recovery_review","provenance","ota_review","from_app_sha256"})) return false;
    const OtaPublisher* publisher = nullptr;
    std::set<std::string> key_ids;
    for (const auto& key : ctx.publishers) {
        if (key.id.empty() || key.id.size() > 64 || !key_ids.insert(key.id).second) return false;
        if (key.id == str(policy,"key_id")) publisher = &key;
    }
    if (!publisher || publisher->revoked || !publisher->development_ota ||
        crypto_sign_verify_detached(signature.data(), payload.data(), payload.size(), publisher->public_key) != 0) return false;
    OtaPolicy accepted;
    if (!equals(policy,"schema",2) || str(policy,"channel") != "development" || str(policy,"purpose") != "ota" ||
        !cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(policy,"installable")) ||
        !integer(policy,"sequence",1,2147483647,accepted.sequence) || accepted.sequence < ctx.minimum_sequence ||
        accepted.sequence <= ctx.confirmed_sequence || str(policy,"profile") != ctx.profile ||
        !equals(policy,"chip_revision",ctx.chip_revision) || !equals(policy,"flash_bytes",ctx.flash_bytes)) return false;
    auto compatibility = cJSON_GetObjectItemCaseSensitive(policy,"compatibility");
    if (!fields(compatibility,{"profile_id","profile_version","layout_id","firmware_lineage"}) ||
        str(compatibility,"profile_id") != ctx.profile_id || !equals(compatibility,"profile_version",ctx.profile_version) ||
        str(compatibility,"layout_id") != ctx.layout_id || str(compatibility,"firmware_lineage") != ctx.lineage) return false;
    accepted.expires_at = expiry(str(policy,"expires_at"));
    if (accepted.expires_at <= ctx.now_utc || !hash(str(policy,"repository_commit"),40) ||
        str(policy,"bootloader_sha256") != ctx.bootloader_sha256 || str(policy,"table_sha256") != ctx.table_sha256) return false;
    for (auto name : {"bootloader_review","c6_review","recovery_review","ota_review"}) if (!review(policy,name)) return false;
    accepted.firmware_version = str(policy,"firmware_version");
    if (accepted.firmware_version.empty() || accepted.firmware_version.size() > 31 ||
        accepted.firmware_version.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._+-") != std::string::npos) return false;
    auto app = cJSON_GetObjectItemCaseSensitive(policy,"app");
    uint32_t size = 0;
    if (!fields(app,{"size","sha256"}) || !integer(app,"size",24,4194304,size) || size > ctx.slot_capacity || !hash(str(app,"sha256"))) return false;
    accepted.app_size = size; accepted.app_sha256 = str(app,"sha256");
    auto previous = cJSON_GetObjectItemCaseSensitive(policy,"from_app_sha256");
    if (!cJSON_IsArray(previous) || cJSON_GetArraySize(previous) < 1 || cJSON_GetArraySize(previous) > 32) return false;
    std::set<std::string> hashes;
    for (auto item = previous->child; item; item = item->next) {
        if (!cJSON_IsString(item) || !item->valuestring || !hash(item->valuestring) ||
            !hashes.insert(item->valuestring).second || accepted.app_sha256 == item->valuestring) return false;
    }
    if (!hashes.count(ctx.running_app_sha256)) return false;
    auto provenance = cJSON_GetObjectItemCaseSensitive(policy,"provenance");
    if (!fields(provenance,{"review_manifest_sha256","archive_sha256","sdkconfig_sha256","dependency_lock_sha256","xiaozhi_commit","esp_idf_commit"})) return false;
    for (auto name : {"review_manifest_sha256","archive_sha256","sdkconfig_sha256","dependency_lock_sha256"}) if (!hash(str(provenance,name))) return false;
    for (auto name : {"xiaozhi_commit","esp_idf_commit"}) if (!hash(str(provenance,name),40)) return false;
    accepted.release_id = identity;
    output = accepted;
    return true;
}
}
