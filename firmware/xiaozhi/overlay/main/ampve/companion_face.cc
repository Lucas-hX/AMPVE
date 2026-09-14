#include "ampve/companion_face.h"

#include "ampve/companion.h"

#include <algorithm>
#include <cstdint>

namespace ampve {
namespace {

constexpr uint32_t kFrameMilliseconds = 50;
constexpr uint32_t kBlinkCycleMilliseconds = 5200;
constexpr uint32_t kBlinkMilliseconds = 150;
constexpr uint32_t kOrange = 0xf15a24;
constexpr uint32_t kIvory = 0xf7f5ee;
constexpr uint32_t kGraphite = 0x20251f;

enum class FaceState : uint8_t { Idle, Connecting, Listening, Speaking, Muted, Error };

struct FaceObjects {
    lv_obj_t* root = nullptr;
    lv_obj_t* eye_arc[2]{};
    lv_obj_t* eye_blink[2]{};
    lv_obj_t* eye_cross[2][2]{};
    lv_obj_t* mouth_smile = nullptr;
    lv_obj_t* mouth_line = nullptr;
    lv_obj_t* mouth_open = nullptr;
    lv_obj_t* mouth_cross[2]{};
};

FaceObjects face;
lv_timer_t* timer = nullptr;
FaceState rendered_state = FaceState::Error;
bool rendered_blink = false;
int rendered_eye_shift = 1000;
int rendered_mouth_height = -1;

lv_obj_t* rounded_bar(lv_obj_t* parent, uint32_t color, int width, int height) {
    auto object = lv_obj_create(parent);
    lv_obj_remove_style_all(object);
    lv_obj_set_size(object, width, height);
    lv_obj_set_style_bg_color(object, lv_color_hex(color), 0);
    lv_obj_set_style_bg_opa(object, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(object, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_transform_pivot_x(object, width / 2, 0);
    lv_obj_set_style_transform_pivot_y(object, height / 2, 0);
    lv_obj_remove_flag(object, LV_OBJ_FLAG_CLICKABLE);
    return object;
}

lv_obj_t* arc(lv_obj_t* parent, uint32_t color, int size, int width, int start, int end) {
    auto object = lv_arc_create(parent);
    lv_obj_remove_style_all(object);
    lv_obj_set_size(object, size, size);
    lv_arc_set_bg_angles(object, start, end);
    lv_obj_set_style_arc_color(object, lv_color_hex(color), LV_PART_MAIN);
    lv_obj_set_style_arc_width(object, width, LV_PART_MAIN);
    lv_obj_set_style_arc_rounded(object, true, LV_PART_MAIN);
    lv_obj_set_style_arc_opa(object, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_remove_flag(object, LV_OBJ_FLAG_CLICKABLE);
    return object;
}

void set_visible(lv_obj_t* object, bool visible) {
    if (visible) lv_obj_remove_flag(object, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
}

void place_cross(lv_obj_t* bars[2], int center_x, int center_y) {
    for (int index = 0; index < 2; ++index) {
        lv_obj_align(bars[index], LV_ALIGN_CENTER, center_x, center_y);
        lv_obj_set_style_transform_rotation(bars[index], index ? -450 : 450, 0);
    }
}

FaceState state() {
    const auto current = companion_state();
    if (current == CompanionState::Error) return FaceState::Error;
    if (current == CompanionState::Connecting) return FaceState::Connecting;
    if (current == CompanionState::Listening) {
        if (companion_muted()) return FaceState::Muted;
        if (companion_speaking()) return FaceState::Speaking;
        return FaceState::Listening;
    }
    return FaceState::Idle;
}

void apply_state(FaceState next) {
    const bool crossed_eyes = next == FaceState::Error;
    for (int eye = 0; eye < 2; ++eye) {
        set_visible(face.eye_arc[eye], !crossed_eyes);
        set_visible(face.eye_blink[eye], false);
        for (auto bar : face.eye_cross[eye]) set_visible(bar, crossed_eyes);
    }
    set_visible(face.mouth_smile, next == FaceState::Idle);
    set_visible(face.mouth_line, next == FaceState::Connecting || next == FaceState::Listening || next == FaceState::Error);
    set_visible(face.mouth_open, next == FaceState::Speaking);
    for (auto bar : face.mouth_cross) set_visible(bar, next == FaceState::Muted);
    rendered_state = next;
    rendered_blink = false;
    rendered_eye_shift = 1000;
    rendered_mouth_height = -1;
}

void update(lv_timer_t*) {
    if (!face.root) return;
    const auto next = state();
    if (next != rendered_state) apply_state(next);

    const uint32_t now = lv_tick_get();
    const bool can_blink = next != FaceState::Error && next != FaceState::Connecting;
    const bool blink = can_blink && now % kBlinkCycleMilliseconds >= kBlinkCycleMilliseconds - kBlinkMilliseconds;
    if (blink != rendered_blink) {
        for (int eye = 0; eye < 2; ++eye) {
            set_visible(face.eye_arc[eye], !blink);
            set_visible(face.eye_blink[eye], blink);
        }
        rendered_blink = blink;
    }

    int eye_shift = 0;
    if (next == FaceState::Connecting) eye_shift = (now / 400) % 2 ? 7 : -2;
    else if (next == FaceState::Listening) {
        constexpr int shifts[] = {-3, 2, 0, 0};
        eye_shift = shifts[(now / 900) % 4];
    }
    if (eye_shift != rendered_eye_shift) {
        lv_obj_align(face.eye_arc[0], LV_ALIGN_CENTER, -112 + eye_shift, -54);
        lv_obj_align(face.eye_arc[1], LV_ALIGN_CENTER, 112 + eye_shift, -54 - (next == FaceState::Connecting ? eye_shift : 0));
        lv_obj_align(face.eye_blink[0], LV_ALIGN_CENTER, -112 + eye_shift, -30);
        lv_obj_align(face.eye_blink[1], LV_ALIGN_CENTER, 112 + eye_shift, -30 - (next == FaceState::Connecting ? eye_shift : 0));
        rendered_eye_shift = eye_shift;
    }

    if (next == FaceState::Speaking) {
        const int target = 22 + companion_output_level() * 38 / 255;
        const int previous = rendered_mouth_height;
        if (rendered_mouth_height < 0) rendered_mouth_height = target;
        else if (target > rendered_mouth_height) rendered_mouth_height = std::min(target, rendered_mouth_height + 9);
        else rendered_mouth_height = std::max(target, rendered_mouth_height - 5);
        if (rendered_mouth_height != previous) {
            lv_obj_set_height(face.mouth_open, rendered_mouth_height);
            lv_obj_align(face.mouth_open, LV_ALIGN_CENTER, 0, 92);
        }
    }
}

}  // namespace

lv_obj_t* companion_face_show(lv_obj_t* parent) {
    face = {};
    face.root = lv_obj_create(parent);
    lv_obj_remove_style_all(face.root);
    lv_obj_set_width(face.root, LV_PCT(100));
    lv_obj_set_flex_grow(face.root, 1);
    lv_obj_set_style_bg_color(face.root, lv_color_hex(kGraphite), 0);
    lv_obj_set_style_bg_opa(face.root, LV_OPA_COVER, 0);
    lv_obj_add_flag(face.root, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_remove_flag(face.root, LV_OBJ_FLAG_SCROLLABLE);

    for (int eye = 0; eye < 2; ++eye) {
        const int center_x = eye ? 112 : -112;
        face.eye_arc[eye] = arc(face.root, kOrange, 104, 20, 180, 360);
        lv_obj_align(face.eye_arc[eye], LV_ALIGN_CENTER, center_x, -54);
        face.eye_blink[eye] = rounded_bar(face.root, kOrange, 82, 18);
        lv_obj_align(face.eye_blink[eye], LV_ALIGN_CENTER, center_x, -30);
        for (auto& bar : face.eye_cross[eye]) bar = rounded_bar(face.root, kOrange, 76, 18);
        place_cross(face.eye_cross[eye], center_x, -32);
    }

    face.mouth_smile = arc(face.root, kIvory, 92, 12, 0, 180);
    lv_obj_align(face.mouth_smile, LV_ALIGN_CENTER, 0, 64);
    face.mouth_line = rounded_bar(face.root, kIvory, 66, 12);
    lv_obj_align(face.mouth_line, LV_ALIGN_CENTER, 0, 92);
    face.mouth_open = lv_obj_create(face.root);
    lv_obj_remove_style_all(face.mouth_open);
    lv_obj_set_size(face.mouth_open, 72, 28);
    lv_obj_set_style_bg_opa(face.mouth_open, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_color(face.mouth_open, lv_color_hex(kIvory), 0);
    lv_obj_set_style_border_width(face.mouth_open, 12, 0);
    lv_obj_set_style_radius(face.mouth_open, LV_RADIUS_CIRCLE, 0);
    lv_obj_align(face.mouth_open, LV_ALIGN_CENTER, 0, 92);
    lv_obj_remove_flag(face.mouth_open, LV_OBJ_FLAG_CLICKABLE);
    for (auto& bar : face.mouth_cross) bar = rounded_bar(face.root, kIvory, 64, 14);
    place_cross(face.mouth_cross, 0, 92);

    rendered_state = FaceState::Error;
    apply_state(state());
    if (!timer) timer = lv_timer_create(update, kFrameMilliseconds, nullptr);
    else {
        lv_timer_set_period(timer, kFrameMilliseconds);
        lv_timer_reset(timer);
        lv_timer_resume(timer);
    }
    update(nullptr);
    return face.root;
}

void companion_face_hide() {
    if (timer) lv_timer_pause(timer);
    face = {};
}

}  // namespace ampve
