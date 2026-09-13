#include "boot_guard.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <limits>
static int read_result=0,set_result=0,commit_result=0,sets=0,commits=0;
static uint32_t stored=0,written=0;
int nvs_get_u32(nvs_handle_t h,const char* key,uint32_t* value) {
    assert(h==7 && !strcmp(key,"boots"));*value=stored;return read_result;
}
int nvs_set_u32(nvs_handle_t h,const char* key,uint32_t value) {
    assert(h==7 && !strcmp(key,"boots"));++sets;written=value;return set_result;
}
int nvs_commit(nvs_handle_t h) {assert(h==7);++commits;return commit_result;}
static void reset() {read_result=set_result=commit_result=sets=commits=0;stored=written=0;}
int main() {
    using ampve::BootAttempt;
    int cases=0;
    for(uint32_t count: {0u,1u,2u}) {
        reset();stored=count;
        assert(ampve::record_boot_attempt(7)==BootAttempt::Ready);
        assert(sets==1 && commits==1 && written==count+1);++cases;
    }
    reset();read_result=ESP_ERR_NVS_NOT_FOUND;stored=99;
    assert(ampve::record_boot_attempt(7)==BootAttempt::Ready && written==1);++cases;
    for(uint32_t count: {3u,4u,std::numeric_limits<uint32_t>::max()}) {
        reset();stored=count;
        assert(ampve::record_boot_attempt(7)==BootAttempt::Recovery && sets==0 && commits==0);++cases;
    }
    for(int error: {-1,2,3}) { // Generic failure, wrong type and corrupt-storage stand-ins.
        reset();read_result=error;
        assert(ampve::record_boot_attempt(7)==BootAttempt::StorageError && sets==0 && commits==0);++cases;
    }
    reset();set_result=-1;
    assert(ampve::record_boot_attempt(7)==BootAttempt::StorageError && sets==1 && commits==0);++cases;
    reset();commit_result=-1;
    assert(ampve::record_boot_attempt(7)==BootAttempt::StorageError && sets==1 && commits==1);++cases;
    reset();assert(ampve::reset_boot_attempts(7) && written==0 && sets==1 && commits==1);++cases;
    reset();set_result=-1;assert(!ampve::reset_boot_attempts(7) && commits==0);++cases;
    reset();commit_result=-1;assert(!ampve::reset_boot_attempts(7) && commits==1);++cases;

    ampve::BootRetryHold hold;
    assert(!hold.update(true,0) && !hold.update(true,9000000));++cases; // Stuck/held at entry.
    assert(!hold.update(false,9000001) && !hold.update(true,10000000));
    assert(!hold.update(true,14999999) && hold.update(true,15000000));++cases;
    for(int i=0;i<100;++i) {assert(!hold.update(true,15000000+i*100000));}
    ++cases;
    assert(!hold.update(false,26000000) && !hold.update(true,27000000));
    assert(!hold.update(false,28000000) && !hold.update(true,29000000));
    assert(!hold.update(true,32000000) && hold.update(true,34000000));++cases;
    assert(!hold.update(false,35000000) && !hold.update(true,36000000));
    assert(!hold.update(true,1) && !hold.update(true,5000000) && hold.update(true,5000001));++cases;
    std::cout << cases << " boot-counter and physical-retry scenarios passed\n";
}
