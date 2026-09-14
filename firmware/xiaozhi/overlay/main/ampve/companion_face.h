#pragma once

#include "lvgl.h"

namespace ampve {

// The face owns one paused-when-hidden LVGL timer and no bitmap assets.
lv_obj_t* companion_face_show(lv_obj_t* parent);
void companion_face_hide();

}  // namespace ampve
