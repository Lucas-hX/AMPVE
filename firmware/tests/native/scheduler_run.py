"""Compile the actual entry point with simulated task creation; no device access."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[3]
with tempfile.TemporaryDirectory(prefix='ampve-scheduler-') as directory:
    root=Path(directory)
    files={
      'freertos/FreeRTOS.h':'#pragma once\n#include <cstdint>\n#define pdPASS 1\n',
      'freertos/task.h':'#pragma once\nint xTaskCreatePinnedToCore(void(*)(void*),const char*,unsigned,void*,int,void*,int);\nvoid vTaskDelete(void*);\n',
      'esp_heap_caps.h':'#pragma once\n#include <cstddef>\n#define MALLOC_CAP_INTERNAL 1\n#define MALLOC_CAP_8BIT 2\nsize_t heap_caps_get_free_size(unsigned);\nsize_t heap_caps_get_largest_free_block(unsigned);\n',
      'esp_rom_sys.h':'#pragma once\nint esp_rom_printf(const char*,...);\n',
      'esp_private/startup_internal.h':'#pragma once\n#define ESP_OK 0\n#define ESP_SYSTEM_INIT_FN(name,stage,core,priority) int name()\n',
      'sdkconfig.h':'#define CONFIG_ESP_MAIN_TASK_STACK_SIZE 4096\n#define CONFIG_ESP_MAIN_TASK_AFFINITY 0\n',
    }
    for name,content in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
    harness=root/'harness.cc'
    harness.write_text(r'''
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <string>
extern "C" void app_main();
int ampve_scheduler_heap();
static void(*pending)(void*);
static bool allocate=true;
static int runtime_calls=0,deletes=0,creates=0;
static std::string logs;
size_t heap_caps_get_free_size(unsigned caps){assert(caps==3);return 50000;}
size_t heap_caps_get_largest_free_block(unsigned caps){assert(caps==3);return 40000;}
int esp_rom_printf(const char* format,...){char b[256];va_list args;va_start(args,format);int n=vsnprintf(b,sizeof(b),format,args);va_end(args);logs+=b;return n;}
int xTaskCreatePinnedToCore(void(*task)(void*),const char* name,unsigned bytes,void* arg,int priority,void* handle,int core){
 assert(bytes==16384&&arg==nullptr&&priority==1&&handle==nullptr&&core==0);
 assert(strcmp(name,"ampve_runtime")==0);++creates;if(allocate)pending=task;return allocate?1:0;
}
void ampve_runtime_start(){++runtime_calls;}
void vTaskDelete(void* task){assert(task==nullptr);++deletes;}
int main(){
 assert(ampve_scheduler_heap()==0);assert(creates==0&&runtime_calls==0);
 assert(logs=="AMPVE_BOOT_HEAP scheduler_pending 50000 40000\n");
 app_main();assert(creates==1&&pending&&runtime_calls==0);
 pending(nullptr);assert(runtime_calls==1&&deletes==1);
 allocate=false;pending=nullptr;app_main();assert(creates==2&&pending==nullptr&&runtime_calls==1);
 assert(logs.find("AMPVE runtime task allocation failed\n")!=std::string::npos);
 puts("Scheduler entry-point fixtures passed: deferred runtime, retained stack/core, cleanup and allocation failure.");
}
''')
    binary=root/'test'
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined','-I'+str(root),str(ROOT/'firmware/xiaozhi/overlay/main/main.cc'),str(harness),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
