"""Preserve NVS and propagate native Wi-Fi initialization failure."""
MANAGER='wifi_manager.cc'
BOARD='main/boards/common/wifi_board.cc'


def transform_manager(source):
    old='''    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "Erasing NVS...");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
'''
    if source.count(old)!=1:raise ValueError('Wi-Fi NVS contract changed')
    return source.replace(old,'    // AMPVE: preserve NVS on every initialization failure; never erase user state.\n')


def prepare(work):
    target=work/'components/78__esp-wifi-connect'/MANAGER
    if not target.exists():return # provisioning.py applies this after making the first override.
    original=(work/'managed_components/78__esp-wifi-connect'/MANAGER).read_text()
    updated=transform_manager(original)
    if target.read_text() not in [original,updated]:raise ValueError('Refusing unrelated Wi-Fi manager changes')
    if target.read_text()!=updated:target.write_text(updated)
