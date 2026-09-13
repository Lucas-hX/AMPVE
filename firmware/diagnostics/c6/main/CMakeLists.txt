idf_component_register(SRCS "probe.c" "integer_stdio.c" INCLUDE_DIRS "." REQUIRES esp_hosted esp_wifi_remote esp_event esp_driver_uart esp_timer)
# The ROM newlib dispatch table otherwise roots unused floating-point stdio.
# This diagnostic emits strings/unsigned integers only; float I/O returns an error.
if(NOT CONFIG_LIBC_NEWLIB_NANO_FORMAT)
    message(FATAL_ERROR "The RAM diagnostic requires the reviewed nano stdio configuration")
endif()
target_link_options(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=_printf_float" "-Wl,--wrap=_scanf_float")
