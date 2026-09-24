#include "lm_bridge.h"
#include "klm.h"
#include "esp_partition.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

bool lm_bridge_reply(const char *question,char *answer,size_t capacity,void (*send)(const char *)) {
    const esp_partition_t *p=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,0x43,"tiny_lm");
    uint32_t header[12];void *blob=NULL;klm *m=NULL;bool ok=false;
    char line[300];int ids[82],token=-1,count=0,n;int64_t begin=esp_timer_get_time();
    uint32_t before=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    if(!answer || capacity<128 || !question || !send)return false;
    answer[0]=0;
#ifdef KLM_BPE
    const char *magic="KLMW8v2\0";
#else
    const char *magic="KLMW8v1\0";
#endif
    if(!p || esp_partition_read(p,0,header,sizeof(header))!=ESP_OK || memcmp(header,magic,8) || header[2]<48 || header[2]>p->size) {
        send("ERROR:LM_MODEL_MISSING_OR_INVALID\n");goto done;
    }
    if(klm_kernel_selftest()) {send("ERROR:LM_KERNEL\n");goto done;}
    blob=heap_caps_aligned_alloc(16,(header[2]+15)&~15u,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!blob || esp_partition_read(p,0,blob,header[2])!=ESP_OK || !(m=klm_open(blob,header[2]))) {
        send("ERROR:LM_LOAD\n");goto done;
    }
    int64_t loaded=esp_timer_get_time();uint32_t during=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    n=klm_encode(m,question,ids,82);
    if(n<0) {send("ERROR:LM_INPUT_USE_KANA_MAX80\n");goto done;}
    send("LM_RUNNING:ON_ESP32_EXPERIMENTAL\n");
    for(int i=0;i<n;i++) {token=klm_step(m,ids[i],NULL);if(token<0)break;vTaskDelay(1);}
    int64_t first=esp_timer_get_time();
    while(token>=0 && token!=3 && count<40) {
        if(klm_append(m,token,answer,capacity)) {token=-1;break;}
        count++;token=klm_step(m,token,NULL);vTaskDelay(1);
    }
    int64_t end=esp_timer_get_time();ok=token==3 && count>0;
    snprintf(line,sizeof(line),"LM_METRICS:load_ms=%lld prefill_ms=%lld decode_ms=%lld prompt_tokens=%d reply_tokens=%d eos=%d model_bytes=%lu workspace=%u psram_during=%lu\n",
        (long long)((loaded-begin)/1000),(long long)((first-loaded)/1000),(long long)((end-first)/1000),n,count,token==3,
        (unsigned long)header[2],(unsigned)klm_workspace_bytes(),(unsigned long)during);send(line);
    if(ok) {send("LM_REPLY:");send(answer);send("\n");}
    else {answer[0]=0;send("ERROR:LM_GENERATION_INCOMPLETE\n");}
done:
    klm_close(m);free(blob);
    snprintf(line,sizeof(line),"LM_DONE:ok=%d psram_before=%lu psram_after=%u largest_after=%u\n",ok,(unsigned long)before,
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),(unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM));send(line);
    return ok;
}
