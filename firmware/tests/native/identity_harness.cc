// Tests only the real streaming identity helper. ESP-IDF image parsing is a stub here.
#include "image_identity.h"
#include "esp_ota_ops.h"
#include "esp_image_format.h"
#include "sodium.h"
#include <algorithm>
#include <cassert>
#include <cstring>
#include <iostream>
#include <vector>
static esp_partition_t partition{0x1000000,4194304,false};
static std::vector<unsigned char> bytes(8193,0x5a);
static bool missing=false, invalid=false, appended=true, io_error=false;
static uint32_t extent=8193;
static size_t reads=0;
const esp_partition_t* esp_ota_get_running_partition() {return missing?nullptr:&partition;}
int esp_image_verify(int mode,const esp_partition_pos_t* position,esp_image_metadata_t* out) {
    assert(mode==ESP_IMAGE_VERIFY_SILENT && position->offset==partition.address && position->size==partition.size);
    out->image_len=extent;out->image.hash_appended=appended;return invalid?-1:ESP_OK;
}
int esp_partition_read(const esp_partition_t* source,size_t offset,void* dest,size_t size) {
    assert(source==&partition && size<=4096 && offset+size<=bytes.size());++reads;
    if(io_error)return -1;
    std::memcpy(dest,bytes.data()+offset,size);return ESP_OK;
}
int main() {
    std::string hash;size_t size=0;
    assert(ampve::running_image_identity(hash,size) && size==8193 && reads==3);
    unsigned char digest[32];char hex[65];crypto_hash_sha256(digest,bytes.data(),bytes.size());
    sodium_bin2hex(hex,sizeof(hex),digest,sizeof(digest));assert(hash==hex);
    bytes.resize(partition.size,0xff);
    assert(ampve::running_image_identity(hash,size) && hash==hex && size==8193);
    auto refused=[&] {hash="stale";size=42;assert(!ampve::running_image_identity(hash,size) && hash.empty() && size==0);};
    missing=true;refused();missing=false;
    partition.encrypted=true;refused();partition.encrypted=false;
    invalid=true;refused();invalid=false;
    appended=false;refused();appended=true;
    extent=23;refused();extent=partition.size+1;refused();extent=8193;
    io_error=true;refused();
    std::cout<<"9 streaming image-identity cases passed; ESP-IDF metadata parser stubbed.\n";
}
