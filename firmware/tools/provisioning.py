'''Create an isolated, traceable local override of the resolved Wi-Fi component.'''
import argparse
import shutil
from pathlib import Path
from prepare import replace
from improv_integration import prepare as prepare_improv
from credential_guard import prepare as prepare_credentials
from wifi_guard import prepare as prepare_wifi


def patch(work):
    source = work/'managed_components/78__esp-wifi-connect'
    target = work/'components/78__esp-wifi-connect'
    if target.exists():
        if not (target/'.ampve-patched').exists():
            raise RuntimeError('Refusing to overwrite an existing component')
        prepare_wifi(work)
        prepare_credentials(work)
        prepare_improv(work)
        return
    if 'version: 3.3.1' not in (source/'idf_component.yml').read_text():
        raise RuntimeError('Unreviewed provisioning component version')
    shutil.copytree(source, target)
    path = target/'wifi_configuration_ap.cc'
    replace(path, '#include "wifi_configuration_ap.h"',
            '#include "wifi_configuration_ap.h"\nextern "C" const char* ampve_wifi_password();')
    replace(path, 'wifi_config.ap.max_connection = 4;', 'wifi_config.ap.max_connection = 1;')
    replace(path, 'wifi_config.ap.authmode = WIFI_AUTH_OPEN;',
            '''// AMPVE: a random per-boot secret is shown only on the local screen.
    const char* password = ampve_wifi_password();
    if (!password || strlen(password) < 16 || strlen(password) > 63) abort();
    strcpy((char*)wifi_config.ap.password, password);
    wifi_config.ap.authmode = WIFI_AUTH_WPA2_PSK;
    wifi_config.ap.pmf_cfg.capable = true;''')
    replace(path, '#include <lwip/ip_addr.h>', '#include <lwip/ip_addr.h>\n#include <lwip/sockets.h>')
    replace(path, '#define TAG "WifiConfigurationAp"', '''// Only the temporary AP interface and explicit local origin may use this portal.
static bool ampve_local_request(httpd_req_t* req) {
    // Browser cross-origin requests cannot add this header without a CORS preflight.
    // HTML navigation stays accessible; API calls require the same-origin page helper.
    if(strcmp(req->uri,"/")!=0 && strncmp(req->uri,"/done.html",10)!=0){
        char header[8]={};
        if(httpd_req_get_hdr_value_str(req,"X-AMPVE-Setup",header,sizeof(header))!=ESP_OK || strcmp(header,"1")!=0)return false;
    }
    char host[64]={}, origin[64]={};
    if(httpd_req_get_hdr_value_str(req,"Host",host,sizeof(host))!=ESP_OK ||
       (strcmp(host,"192.168.4.1")!=0 && strcmp(host,"192.168.4.1:80")!=0))return false;
    if(httpd_req_get_hdr_value_len(req,"Origin") &&
       (httpd_req_get_hdr_value_str(req,"Origin",origin,sizeof(origin))!=ESP_OK ||
        strcmp(origin,"http://192.168.4.1")!=0))return false;
    return true;
}
#define TAG "WifiConfigurationAp"''')
    replace(path, '    config.max_uri_handlers = 24;', '''    config.open_fn = [](httpd_handle_t, int fd) -> esp_err_t {
        sockaddr_in local={};socklen_t length=sizeof(local);
        if(getsockname(fd,reinterpret_cast<sockaddr*>(&local),&length)!=0 ||
           local.sin_family!=AF_INET || ntohl(local.sin_addr.s_addr)!=0xC0A80401)return ESP_FAIL;
        return ESP_OK;
    };
    config.max_uri_handlers = 24;''')
    replace(path, '.handler = [](httpd_req_t *req) -> esp_err_t {',
            '.handler = [](httpd_req_t *req) -> esp_err_t {\n            if(!ampve_local_request(req))return httpd_resp_send_err(req,HTTPD_403_FORBIDDEN,"Local setup only");')
    for page in ['wifi_configuration.html', 'wifi_configuration_done.html']:
        tag = '<script type="text/javascript">' if page == 'wifi_configuration.html' else '<script>'
        replace(target/'assets'/page, tag, tag+"""
        const ampveFetch = window.fetch.bind(window);
        window.fetch = (url, options = {}) => ampveFetch(url, {
            ...options, headers: {...options.headers, 'X-AMPVE-Setup': '1'}
        });""")
    html = target/'assets/wifi_configuration.html'
    replace(html, 'let html = `<span>${ssid}</span>`;',
            'const safeName = document.createElement("span"); safeName.textContent = ssid;\n                let html = safeName.outerHTML;')
    replace(html, "            try {\n                const response = await fetch('/submit', {",
            "            document.getElementById('password').value = '';\n            try {\n                const response = await fetch('/submit', {")
    replace(path, '#define TAG "WifiConfigurationAp"', '''static std::string ampve_json_string(const char* text) {
    auto value=cJSON_CreateString(text);char* raw=cJSON_PrintUnformatted(value);
    std::string result=raw?raw:"null";cJSON_free(raw);cJSON_Delete(value);return result;
}
#define TAG "WifiConfigurationAp"''')
    replace(path, 'json_str += "\\"" + ssid.ssid + "\\",";',
            'json_str += ampve_json_string(ssid.ssid.c_str()) + ",";')
    replace(path, 'char buf[128];', 'char buf[512];')
    replace(path, '"{\\"ssid\\":\\"%s\\",\\"rssi\\":%d,\\"authmode\\":%d}"',
            '"{\\"ssid\\":%s,\\"rssi\\":%d,\\"authmode\\":%d}"')
    replace(path, '(char *)this_->ap_records_[i].ssid, this_->ap_records_[i].rssi, this_->ap_records_[i].authmode);',
            'ampve_json_string((char *)this_->ap_records_[i].ssid).c_str(), this_->ap_records_[i].rssi, this_->ap_records_[i].authmode);')
    replace(work/'main/idf_component.yml', '78/esp-wifi-connect: ~3.3.1',
            '78/esp-wifi-connect:\n    version: "3.3.1"\n    override_path: ../components/78__esp-wifi-connect')
    (target/'.ampve-patched').write_text('3.3.1\n')
    prepare_wifi(work)
    prepare_credentials(work)
    prepare_improv(work)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--work', type=Path, required=True)
    patch(parser.parse_args().work.resolve())
