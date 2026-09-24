// Local synthesize-then-play bridge. Amp stays disabled until zero-filled DMA/mute checks.
#include "tts_bridge.h"
#include <math.h>
#include <string.h>
#include <stdio.h>
#include "driver/usb_serial_jtag.h"
#include "esp_codec_dev.h"
#include "esp_codec_dev_defaults.h"
#include "esp_partition.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "rlcd42_board.h"
#include "rlcd42_display.h"
#include "saanotts.h"
#include "saanotts_stream.h"
#include "g2p.h"
#include "echo_dsp.h"

static saan_weights weights;
static esp_partition_mmap_handle_t model_map;
static esp_codec_dev_handle_t speaker;
static bool ready;
static void trace(const char *stage,int value) {
    char line[96];int n=snprintf(line,sizeof(line),"TTS_STAGE:%s value=%d\n",stage,value);
    usb_serial_jtag_write_bytes(line,n,pdMS_TO_TICKS(20));
}

bool tts_bridge_init(const audio_codec_data_if_t *data) {
    const esp_partition_t *part=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,0x41,"tts");
    const void *blob=NULL;
    if(!part||esp_partition_mmap(part,0,part->size,ESP_PARTITION_MMAP_DATA,&blob,&model_map)!=ESP_OK) return false;
    if(saan_weights_open(&weights,blob,part->size)!=SAAN_OK) return false;
    audio_codec_i2c_cfg_t ctrl_cfg={.port=0,.addr=ES8311_CODEC_DEFAULT_ADDR,.bus_handle=rlcd42_board_i2c_bus()};
    const audio_codec_ctrl_if_t *ctrl=audio_codec_new_i2c_ctrl(&ctrl_cfg);
    const audio_codec_gpio_if_t *gpio=audio_codec_new_gpio();
    if(!ctrl||!gpio) return false;
    es8311_codec_cfg_t cfg={.ctrl_if=ctrl,.gpio_if=gpio,.codec_mode=ESP_CODEC_DEV_WORK_MODE_DAC,
        .pa_pin=GPIO_NUM_NC,.master_mode=false,.use_mclk=true,.hw_gain={.pa_gain=6.0f}};
    const audio_codec_if_t *codec=es8311_codec_new(&cfg);if(!codec) return false;
    esp_codec_dev_cfg_t dev={.dev_type=ESP_CODEC_DEV_TYPE_OUT,.codec_if=codec,.data_if=data};
    speaker=esp_codec_dev_new(&dev);
    ready=speaker!=NULL;return ready;
}
static bool reg_is(int addr,int mask,int value) {
    int read=0;int err=esp_codec_dev_read_reg(speaker,addr,&read);
    if(err || (read&mask)!=value) { trace("reg_addr",addr);trace("reg_value",read);trace("reg_error",err); }
    return err==ESP_CODEC_DEV_OK && (read&mask)==value;
}
bool tts_bridge_say(const char *kana,i2s_chan_handle_t tx) {
    if(!ready||!kana||!rlcd42_board_amp_is_disabled()) return false;
    int32_t ids[350],count=0;
    saan_g2p_status gs=saan_g2p(kana,strlen(kana),ids,350,&count,NULL);
    trace("g2p",gs);trace("ids",count);
    if(gs!=SAAN_G2P_OK || count<=3) return false;
    const size_t arena_bytes=208*1024;
    void *work=heap_caps_aligned_alloc(16,arena_bytes,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    if(!work) work=heap_caps_aligned_alloc(16,arena_bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    float *chunk=heap_caps_malloc(SAAN_CHUNK*SAAN_HOP*sizeof(float),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    int16_t *pcm=NULL;bool opened=false,ok=false;
    if(!work||!chunk) goto finish;
    saan_arena arena;saan_arena_init(&arena,work,arena_bytes);
    saan_stream stream;
    // Duration scaling preserves pitch. User requested another speed increase.
    saan_status ss=saan_stream_init(&stream,&weights,&arena,ids,count,SAAN_S_V*0.95f);
    trace("init",ss);
    if(ss!=SAAN_OK) goto finish;
    if(arena.used!=saan_stream_arena_used(count)) goto finish;
    size_t capacity=(size_t)stream.n_frames*SAAN_HOP;
    if(capacity==0 || capacity>SAAN_SR*15) goto finish;
    pcm=heap_caps_malloc(capacity*sizeof(int16_t),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!pcm) goto finish;
    size_t used=0;
    for(;;) {
        int32_t frames=0;
        if(saan_stream_pull(&stream,chunk,&frames)!=SAAN_OK) goto finish;
        if(frames==0) break;
        if(frames<0 || frames>SAAN_CHUNK) goto finish;
        size_t n=(size_t)frames*SAAN_HOP;
        if(used+n>capacity) goto finish;
        for(size_t i=0;i<n;i++) {
            float value=chunk[i];
            if(!isfinite(value)) goto finish;
            if(value>0.999f) value=0.999f;
            if(value< -0.999f) value=-0.999f;
            pcm[used+i]=(int16_t)lrintf(value*32767.0f);
        }
        used+=n;vTaskDelay(1);
    }
    free(work);work=NULL;free(chunk);chunk=NULL;
    // CharaDock filters/compressor/limiter run locally, before any DMA playback.
    double raw_energy=0;for(size_t i=0;i<used;i++) raw_energy+=(double)pcm[i]*pcm[i];
    trace("raw_rms",(int)sqrt(raw_energy/used));
    echo_dsp dsp;size_t shaped=0;
    if(!echo_dsp_init_rlcd(&dsp)) goto finish;
    for(size_t off=0;off<used;off+=256) {
        size_t n=used-off;if(n>256) n=256;
        shaped+=echo_dsp_push(&dsp,pcm+off,n,pcm+shaped);
    }
    shaped+=echo_dsp_finish(&dsp,pcm+shaped);
    if(dsp.faults || shaped!=used) goto finish;
    double shaped_energy=0;int shaped_peak=0;
    for(size_t i=0;i<used;i++) { shaped_energy+=(double)pcm[i]*pcm[i];int a=abs(pcm[i]);if(a>shaped_peak) shaped_peak=a; }
    trace("dsp_rms",(int)sqrt(shaped_energy/used));trace("dsp_peak",shaped_peak);
    trace("dsp_charadock",1);
    trace("samples",used);
    // The input device must be closed by the caller before playback changes clocks.
    esp_err_t te=i2s_channel_enable(tx);trace("tx_enable",te);
    // The shared codec driver may already have enabled this initialized channel.
    if(te!=ESP_OK && te!=ESP_ERR_INVALID_STATE) goto finish;
    esp_codec_dev_sample_info_t format={.sample_rate=SAAN_SR,.channel=2,.bits_per_sample=16,.mclk_multiple=256};
    int ce=esp_codec_dev_open(speaker,&format);trace("codec_open",ce);
    if(ce!=ESP_CODEC_DEV_OK) goto finish;
    opened=true;
    trace("mute_checks",0);
    if(esp_codec_dev_set_out_vol(speaker,0)!=ESP_CODEC_DEV_OK || !reg_is(0x32,0xff,0)) goto finish;
    if(esp_codec_dev_set_out_mute(speaker,true)!=ESP_CODEC_DEV_OK || !reg_is(0x31,0x60,0x60)) goto finish;
    trace("zero_fill",0);
    int16_t stereo[512]={0};
    for(int i=0;i<6;i++) { int e=esp_codec_dev_write(speaker,stereo,sizeof(stereo));if(e!=ESP_CODEC_DEV_OK) { trace("zero_error",e);goto finish; } }
    trace("amp_enable",0);
    if(!rlcd42_board_set_amp_enabled(true)) goto finish;
    trace("ramp",0);
    // 100 is the official factory ceiling, never exceed it or bypass the limiter.
    for(int volume=2;volume<=100;volume+=2) {
        if(esp_codec_dev_set_out_vol(speaker,volume)!=ESP_CODEC_DEV_OK || !reg_is(0x32,0xff,0x56+volume)) goto finish;
        vTaskDelay(pdMS_TO_TICKS(3));
    }
    if(esp_codec_dev_set_out_mute(speaker,false)!=ESP_CODEC_DEV_OK || !reg_is(0x31,0x60,0)) goto finish;
    rlcd42_display_set_speaking(true);
    for(size_t off=0;off<used;off+=256) {
        size_t n=used-off;if(n>256) n=256;
        int peak=0;
        for(size_t i=0;i<n;i++) {
            int value=pcm[off+i];int a=value<0?-value:value;if(a>peak) peak=a;
            stereo[2*i]=stereo[2*i+1]=value;
        }
        if(esp_codec_dev_write(speaker,stereo,n*4)!=ESP_CODEC_DEV_OK) goto finish;
        rlcd42_display_set_level((uint8_t)(peak>12000?255:peak*255/12000));
    }
    memset(stereo,0,sizeof(stereo));
    for(int i=0;i<6;i++) if(esp_codec_dev_write(speaker,stereo,sizeof(stereo))!=ESP_CODEC_DEV_OK) goto finish;
    vTaskDelay(pdMS_TO_TICKS(100));ok=true;
finish:
    rlcd42_board_set_amp_enabled(false);
    if(opened) { esp_codec_dev_set_out_mute(speaker,true);esp_codec_dev_set_out_vol(speaker,0);esp_codec_dev_close(speaker); }
    else i2s_channel_disable(tx);
    rlcd42_display_set_speaking(false);
    free(pcm);free(work);free(chunk);return ok;
}
