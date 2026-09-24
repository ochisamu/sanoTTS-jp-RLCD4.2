// Offline RLCD4.2 STT -> phonemes -> kana -> sanoTTS. No Wi-Fi.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "driver/usb_serial_jtag.h"
#include "esp_codec_dev.h"
#include "esp_codec_dev_defaults.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_partition.h"
#include "esp_timer.h"
#include "ctc_runtime.h"
#include "phonemes.h"
#include "speech_trim.h"
#include "voice_buttons.h"
#include "tts_bridge.h"
#include "lm_bridge.h"
#include "reply_support.h"
#include "klm.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "rlcd42_board.h"
#include "rlcd42_display.h"

#define RATE 16000
#define FRAMES 256
#define MAX_SECONDS 5
static esp_codec_dev_handle_t mic;
static i2s_chan_handle_t rx,tx;
static bool tts_ready;
static int16_t *pcm;
static const void *stt_blob;
static size_t stt_size;
static esp_partition_mmap_handle_t stt_map;
static int64_t stt_started;
static bool reply_capture;
static void ask_lm(const char *question,bool speak);
static unsigned button_mask(void) {
    return (gpio_get_level(18)?0:1)|(gpio_get_level(0)?0:2);
}

static bool send_bytes(const void *data, size_t n) {
    const char *p = data;
    while (n) {
        // IDF enqueues a whole item; it cannot accept a 320KB item in a 4KB ring.
        size_t chunk = n > 512 ? 512 : n;
        int sent = usb_serial_jtag_write_bytes(p, chunk, pdMS_TO_TICKS(20));
        if (sent <= 0) return false;
        p += sent; n -= sent;
    }
    return true;
}
static void say(const char *s) { send_bytes(s, strlen(s)); }
void ctc_progress(const char *stage) {
    char line[96];snprintf(line,sizeof(line),"STAGE:%s ms=%lld\n",stage,(long long)((esp_timer_get_time()-stt_started)/1000));say(line);
}

static bool init_mic(void) {
    if (!rlcd42_board_i2c_present(0x40)) return false;
    i2s_chan_config_t ch = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    ch.dma_desc_num = 6; ch.dma_frame_num = FRAMES;
    ch.auto_clear=true;
    ESP_ERROR_CHECK(i2s_new_channel(&ch, &tx, &rx));
    i2s_std_config_t cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {.mclk=GPIO_NUM_16, .bclk=GPIO_NUM_9, .ws=GPIO_NUM_45,
                     .dout=GPIO_NUM_8, .din=GPIO_NUM_10},
    };
    ESP_ERROR_CHECK(i2s_channel_init_std_mode(rx, &cfg));
    ESP_ERROR_CHECK(i2s_channel_init_std_mode(tx, &cfg));
    ESP_ERROR_CHECK(i2s_channel_enable(rx));
    audio_codec_i2s_cfg_t data_cfg = {.port=0, .rx_handle=rx,.tx_handle=tx};
    const audio_codec_data_if_t *data = audio_codec_new_i2s_data(&data_cfg);
    audio_codec_i2c_cfg_t ctrl_cfg = {.port=0, .addr=ES7210_CODEC_DEFAULT_ADDR,
                                    .bus_handle=rlcd42_board_i2c_bus()};
    const audio_codec_ctrl_if_t *ctrl = audio_codec_new_i2c_ctrl(&ctrl_cfg);
    if (!data || !ctrl) return false;
    es7210_codec_cfg_t adc_cfg = {.ctrl_if=ctrl,
        .mic_selected=ES7210_SEL_MIC1 | ES7210_SEL_MIC2, .mclk_div=256};
    const audio_codec_if_t *adc = es7210_codec_new(&adc_cfg);
    if (!adc) return false;
    esp_codec_dev_cfg_t dev_cfg = {.dev_type=ESP_CODEC_DEV_TYPE_IN, .codec_if=adc, .data_if=data};
    mic = esp_codec_dev_new(&dev_cfg);
    if (!mic) return false;
    esp_codec_dev_sample_info_t format = {.sample_rate=RATE, .channel=2, .bits_per_sample=16};
    if (esp_codec_dev_open(mic, &format) != ESP_CODEC_DEV_OK) return false;
    if (esp_codec_dev_set_in_gain(mic, 24.0f) != ESP_CODEC_DEV_OK) return false;
    tts_ready=tts_bridge_init(data);
    // Only drain/capture following an explicit host command, never at boot.
    return rlcd42_board_amp_is_disabled();
}

static bool capture(bool transmit) {
    if (!rlcd42_board_amp_is_disabled()) { say("ERROR:AMP\n"); return false; }
    rlcd42_display_status(reply_capture?"CHAT LISTEN 5 SEC":"ECHO LISTEN 5 SEC");
    const size_t samples = RATE * MAX_SECONDS * 2;
    int16_t discard[FRAMES * 2];
    say("RECORDING:5\n");
    for (int i=0; i<8; ++i)
        if (esp_codec_dev_read(mic, discard, sizeof(discard)) != ESP_CODEC_DEV_OK) {
            say("ERROR:READ\n"); return false;
        }
    for (size_t off=0; off<samples; ) {
        size_t count = samples-off;
        if (count > FRAMES*2) count=FRAMES*2;
        if (esp_codec_dev_read(mic, pcm+off, count*sizeof(int16_t)) != ESP_CODEC_DEV_OK) {
            say("ERROR:READ\n"); return false;
        }
        off += count;
    }
    double squares[2]={0}; int peak[2]={0}; long clips[2]={0};
    for (size_t i=0; i<samples; ++i) {
        int value=pcm[i], a=abs(value), c=i%2;
        squares[c]+=(double)value*value;
        if (a>peak[c]) peak[c]=a;
        if (a>=32760) clips[c]++;
    }
    char header[256];
    snprintf(header,sizeof(header),"PCM:%u:16000:2:16\n",(unsigned)(samples*2));
    if (transmit && (!send_bytes(header,strlen(header)) || !send_bytes(pcm,samples*2))) return false;
    snprintf(header,sizeof(header),"\nSTATS:rms=%.2f,%.2f peak=%d,%d clips=%ld,%ld psram_free=%u\nDONE\n",
        sqrt(squares[0]/(samples/2)),sqrt(squares[1]/(samples/2)),peak[0],peak[1],clips[0],clips[1],
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    say(header);
    return true;
}

static void speak_kana(const char *kana,const char *display_text) {
    rlcd42_display_spoken(display_text?display_text:kana);
    if(!tts_ready) { say("ERROR:TTS_NOT_READY\n");return; }
    rlcd42_display_status("SYNTHESIZING");
    if(esp_codec_dev_close(mic)!=ESP_CODEC_DEV_OK) { say("ERROR:MIC_CLOSE\n");return; }
    // ESP32-S3 full-duplex I2S requires RX running for TX DMA to advance.
    esp_err_t prime=i2s_channel_enable(rx);
    if(prime!=ESP_OK && prime!=ESP_ERR_INVALID_STATE) { say("ERROR:RX_CLOCK\n");return; }
    bool ok=tts_bridge_say(kana,tx);
    esp_err_t clock=i2s_channel_enable(rx);
    esp_codec_dev_sample_info_t format={.sample_rate=RATE,.channel=2,.bits_per_sample=16,.mclk_multiple=256};
    if((clock!=ESP_OK && clock!=ESP_ERR_INVALID_STATE) || esp_codec_dev_open(mic,&format)!=ESP_CODEC_DEV_OK || esp_codec_dev_set_in_gain(mic,24.0f)!=ESP_CODEC_DEV_OK) {
        say("ERROR:MIC_REOPEN\n");rlcd42_display_show_error("MIC REOPEN");return;
    }
    say(ok?"ECHO_DONE:ON_ESP32\n":"ERROR:TTS\n");
    char stack_line[64];snprintf(stack_line,sizeof(stack_line),"STACK_FREE_MIN:%u\n",(unsigned)uxTaskGetStackHighWaterMark(NULL));say(stack_line);
    rlcd42_display_set_ready();
}

static void run_stt(const float *audio,int samples,bool speak,char *recognized,size_t capacity) {
    if(recognized && capacity) recognized[0]=0;
    if(!stt_blob || !rlcd42_board_amp_is_disabled()) { say("ERROR:STT_NOT_READY\n");return; }
    say("STT_RUNNING:ON_ESP32\n");
    rlcd42_display_status("RECOGNIZING");
    float *logits=NULL;int frames=0,vocab=0;
    int64_t start=esp_timer_get_time();
    stt_started=start;
    int err=ctc_run(stt_blob,stt_size,audio,samples,5,&logits,&frames,&vocab);
    char msg[256];
    if(err) { snprintf(msg,sizeof(msg),"ERROR:STT:%d\n",err);say(msg);return; }
    say("PHONEME_IDS:"); int last=-1;uint32_t hash=2166136261u;int ids[256],count=0;
    for(int t=0;t<frames;t++) {
        int best=0;for(int v=1;v<vocab;v++) if(logits[t*vocab+v]>logits[t*vocab+best]) best=v;
        hash=(hash^(uint32_t)best)*16777619u;
        if(best && best!=last) {
            snprintf(msg,sizeof(msg),"%d,",best);say(msg);
            if(count<256) ids[count++]=best;
            else { ctc_free(logits);say("ERROR:TOO_LONG\n");return; }
        }
        last=best;
    }
    ctc_free(logits);
    snprintf(msg,sizeof(msg),"\nSTT_DONE:ms=%lld frames=%d hash=%08lx psram_free=%u\n",
        (long long)((esp_timer_get_time()-start)/1000),frames,(unsigned long)hash,
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    say(msg);
    char kana[1024];int dropped=phonemes_to_kana(ids,count,kana,sizeof(kana));
    if(dropped<0||dropped>count/5||!count||!kana[0]) { say("ERROR:UNRELIABLE_PHONEMES\n");rlcd42_display_show_error("TRY AGAIN");return; }
    say("KANA:");say(kana);say("\n");
    rlcd42_display_heard(kana);
    if(recognized && capacity) {
        if(strlen(kana)>=capacity) {say("ERROR:STT_TEXT_TOO_LONG\n");return;}
        memcpy(recognized,kana,strlen(kana)+1);
    }
    if(speak) speak_kana(kana,NULL);else rlcd42_display_set_ready();
}
static void test_stt(bool speak,bool reply) {
    rlcd42_display_begin(reply);
    const esp_partition_t *part=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,0x42,"testaudio");
    uint32_t samples=0;
    if(!part || esp_partition_read(part,0,&samples,4)!=ESP_OK || samples<16000 || samples>128000) {
        say("ERROR:TEST_AUDIO\n");return;
    }
    float *audio=heap_caps_malloc(samples*sizeof(float),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!audio) { say("ERROR:TEST_ALLOC\n");return; }
    char kana[1024]={0};
    if(esp_partition_read(part,4,audio,samples*sizeof(float))==ESP_OK) run_stt(audio,samples,speak,reply?kana:NULL,sizeof(kana));
    else say("ERROR:TEST_READ\n");
    free(audio);
    if(reply && kana[0]) ask_lm(kana,true);
}
static void listen_stt(bool reply) {
    rlcd42_display_begin(reply);
    reply_capture=reply;
    say(reply?"VOICE_MODE:REPLY\n":"VOICE_MODE:ECHO\n");
    if(!capture(false)) return;
    const int n=RATE*MAX_SECONDS;
    double sums[2]={0},squares[2]={0};
    for(int i=0;i<n;i++) for(int c=0;c<2;c++) { double v=pcm[2*i+c];sums[c]+=v;squares[c]+=v*v; }
    int channel=squares[1]>squares[0]?1:0;float mean=sums[channel]/n;
    float rms=sqrtf(fmaxf(0,(float)(squares[channel]/n)-mean*mean))/32768.0f;
    float *audio=heap_caps_malloc(n*sizeof(float),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!audio) { say("ERROR:AUDIO_ALLOC\n");return; }
    float peak=1e-6f;
    for(int i=0;i<n;i++) { audio[i]=(pcm[2*i+channel]-mean)/32768.0f;if(fabsf(audio[i])>peak) peak=fabsf(audio[i]); }
    int begin=0,end=n;
    int detected=speech_trim(audio,n,&begin,&end);
    // A short phrase is diluted by several seconds of silence. Inspect local
    // speech windows before applying the full-recording quiet fallback.
    if(!detected && rms<0.002f) {
        free(audio);say("NO_SPEECH:QUIET_PRESS_KEY_RETRY\n");
        rlcd42_display_status("NO SPEECH - RETRY");return;
    }
    float gain=fminf(20.0f,fminf(0.05f/fmaxf(rms,1e-6f),0.9f/peak));
    char trim_line[96];snprintf(trim_line,sizeof(trim_line),"AUDIO_REGION:begin_ms=%d end_ms=%d input_ms=%d\n",begin/16,end/16,(end-begin)/16);say(trim_line);
    for(int i=0;i<n;i++) audio[i]*=gain;
    char kana[1024]={0};
    run_stt(audio+begin,end-begin,!reply,reply?kana:NULL,sizeof(kana));free(audio);
    // Release recording/STT work before loading the LM. Never reuse an old reply.
    if(reply && kana[0]) ask_lm(kana,true);
}

static void ask_lm(const char *question,bool speak) {
    if(!rlcd42_board_amp_is_disabled()) {say("ERROR:AMP\n");return;}
    char answer[256];rlcd42_display_status("THINKING DEMO");
    reply_fact fact;
    bool from_knowledge=reply_knowledge_lookup(question,&fact);
    bool ok;
    const char *display;
    if(from_knowledge) {
        snprintf(answer,sizeof(answer),"%s",fact.reading);display=fact.display;ok=true;
        say("REPLY_SOURCE:LOCAL_KNOWLEDGE:");say(fact.id);say("\n");
        say("LM_REPLY:");say(answer);say("\nLM_DONE:ok=1 source=knowledge\n");
    } else {
        say("REPLY_SOURCE:SLM\n");
        ok=lm_bridge_reply(question,answer,sizeof(answer),say);
        display=reply_display_text(answer);
    }
    if(ok){say("DISPLAY_REPLY:");say(display);say("\n");}
    if(ok && speak) {
        char intermediate[256];
        if(klm_tts_text(answer,intermediate,sizeof(intermediate))>0)speak_kana(intermediate,display);
        else {say("ERROR:LM_TTS_TEXT\n");rlcd42_display_show_error("REPLY FAILED");}
    }
    else if(!ok) rlcd42_display_show_error("REPLY FAILED");
    else {rlcd42_display_spoken(display);rlcd42_display_set_ready();}
}

void app_main(void) {
    if (!rlcd42_board_init()) return;
    if (!rlcd42_display_init()) return;
    rlcd42_display_set_ready();
    if(rlcd42_battery_init()) { rlcd42_battery_status_t battery;if(rlcd42_battery_read(&battery)) rlcd42_display_set_battery(&battery); }
    pcm=heap_caps_malloc(RATE*MAX_SECONDS*2*sizeof(int16_t), MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if (!pcm || !init_mic()) { rlcd42_display_show_error("MIC INIT FAILED"); return; }
    usb_serial_jtag_driver_config_t usb=USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    usb.tx_buffer_size=4096; usb.rx_buffer_size=1024;
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));
    gpio_config_t key={.pin_bit_mask=(1ULL<<18)|(1ULL<<0),.mode=GPIO_MODE_INPUT,.pull_up_en=GPIO_PULLUP_ENABLE};
    ESP_ERROR_CHECK(gpio_config(&key));
    const esp_partition_t *part=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,0x40,"stt");
    if(part && ctc_kernel_selftest()==0 && esp_partition_mmap(part,0,part->size,ESP_PARTITION_MMAP_DATA,&stt_blob,&stt_map)==ESP_OK)
        stt_size=part->size;
    // No log messages may interleave with binary PCM after this point.
    esp_log_level_set("*", ESP_LOG_NONE);
    say("RLCD42_MIC_PROBE:v1 READY PA_OFF commands=ID,REC\n");
    char line[400]; size_t n=0; bool overflow=false,armed=false;
    voice_buttons buttons;voice_buttons_reset(&buttons,button_mask(),esp_timer_get_time());
    while (true) {
        rlcd42_display_tick();
        unsigned action=voice_buttons_update(&buttons,button_mask(),esp_timer_get_time());
        if(action) {
            if(action==1 && armed) {armed=false;reply_capture=false;capture(true);}
            else {armed=false;listen_stt(action==2);}
            voice_buttons_reset(&buttons,button_mask(),esp_timer_get_time());
        }
        char c;
        if (usb_serial_jtag_read_bytes(&c,1,pdMS_TO_TICKS(50))!=1) continue;
        if (c=='\r') continue;
        if (c=='\n') {
            if(overflow) {overflow=false;n=0;say("ERROR:LONG_COMMAND\n");continue;}
            line[n]='\0';
            if (!strcmp(line,"ID")) say("RLCD42_MIC_PROBE:v1 READY PA_OFF commands=ID,REC,TEST,ECHO,LISTEN,CHAT,TESTCHAT,SAY,ASK,ASKSAY,LMBENCH buttons=KEY:ECHO,BOOT:REPLY\n");
            else if (!strcmp(line,"LMBENCH")) ask_lm("きょうはつかれた",false);
            else if (!strncmp(line,"ASK ",4)) {rlcd42_display_begin(true);rlcd42_display_heard(line+4);ask_lm(line+4,false);}
            else if (!strncmp(line,"ASKSAY ",7)) {rlcd42_display_begin(true);rlcd42_display_heard(line+7);ask_lm(line+7,true);}
            else if (!strcmp(line,"REC")) {reply_capture=false;capture(true);}
            else if (!strcmp(line,"TEST")) test_stt(false,false);
            else if (!strcmp(line,"ECHO")) test_stt(true,false);
            else if (!strcmp(line,"TESTCHAT")) test_stt(false,true);
            else if (!strcmp(line,"LISTEN")) listen_stt(false);
            else if (!strcmp(line,"CHAT")) listen_stt(true);
            else if (!strcmp(line,"SAY")) {rlcd42_display_begin(false);speak_kana("きょおわいいてんきですね",NULL);}
            else if (!strcmp(line,"ARM")) { armed=true; say("ARMED:PRESS_KEY_THEN_SPEAK\n"); }
            else say("ERROR:COMMAND\n");
            n=0;
            voice_buttons_reset(&buttons,button_mask(),esp_timer_get_time());
        } else if (!overflow && n<sizeof(line)-1) line[n++]=c;
        else overflow=true;
    }
}
