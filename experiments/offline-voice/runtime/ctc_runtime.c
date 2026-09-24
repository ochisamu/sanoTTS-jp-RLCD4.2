// Minimal portable Moonshine encoder/phoneme CTC runtime. Not upstream Moonshine code.
#include "ctc_runtime.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#endif

// Yield periodically, not once per tiny matrix tile. Keep the idle task and
// peripherals scheduled without changing any arithmetic or model parameters.
// Like the math tables below, this runtime is single-inference/non-reentrant.
#ifdef ESP_PLATFORM
static int64_t last_yield_us;
static void cooperate(void) {
    int64_t now=esp_timer_get_time();
    if(now-last_yield_us>=20000) {
        vTaskDelay(1);
        last_yield_us=esp_timer_get_time();
    }
}
#endif

#define H 288
#define FF 1152
#define HEADS 8
#define HD 36
#define ROT 32
typedef struct { char name[64]; uint32_t rows,cols,stride,kind,data,scale,pad[2]; } Tensor;
typedef struct { const uint8_t *blob; size_t size; uint32_t count,layers,vocab; const Tensor *tensors; int qa; } Model;
static void *alloc(size_t n) {
    n=(n+15)&~(size_t)15;
#ifdef ESP_PLATFORM
    return heap_caps_aligned_alloc(16,n,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
#else
    return aligned_alloc(16,n);
#endif
}
void ctc_free(void *p) { free(p); }
__attribute__((weak)) void ctc_progress(const char *stage) { (void)stage; }
static void *fast_alloc(size_t n) {
#ifdef ESP_PLATFORM
    void *p=heap_caps_aligned_alloc(16,(n+15)&~(size_t)15,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    if(p) return p;
#endif
    return alloc(n);
}
static const Tensor *find(const Model *m,const char *name) {
    for(uint32_t i=0;i<m->count;i++) if(!strcmp(m->tensors[i].name,name)) return &m->tensors[i];
    return NULL;
}
static const float *vector(const Model *m,const char *name,int n) {
    const Tensor *t=find(m,name);
    return t && t->kind==0 && t->rows==(uint32_t)n ? (const float *)(m->blob+t->data):NULL;
}
static float gelu(float v) { return 0.5f*v*(1.0f+erff(v*0.7071067811865475f)); }
static float gelu_table[2049],tanh_table[2049],exp_table[1025];
static int math_ready;
static void init_math(void) {
    if(math_ready) return;
    for(int i=0;i<=2048;i++) { float x=(float)i/128-8;gelu_table[i]=gelu(x);tanh_table[i]=tanhf(x); }
    for(int i=0;i<=1024;i++) exp_table[i]=expf((float)i/64-16);
    math_ready=1;
}
static float interpolate(const float *table,float p,int last) {
    if(p>=last) return table[last];
    int i=(int)p;float f=p-i;return table[i]+f*(table[i+1]-table[i]);
}
static float fast_gelu(float x) { if(x<=-8) return 0;if(x>=8) return x;return interpolate(gelu_table,(x+8)*128,2048); }
static float fast_tanh(float x) { if(x<=-8) return -1;if(x>=8) return 1;return interpolate(tanh_table,(x+8)*128,2048); }
static float fast_exp(float x) { if(x<=-16) return 0;if(x>=0) return 1;return interpolate(exp_table,(x+16)*64,1024); }
static int32_t dot(const int8_t *a,const int8_t *b,int n) {
#if defined(ESP_PLATFORM) && defined(CONFIG_IDF_TARGET_ESP32S3)
    // Adapted from sanoTTS-jp saan_dot_i8_pie (MIT; see licenses/sanoTTS-jp-MIT.txt).
    // Both pointers aligned to 16 bytes; n is a positive multiple of 16.
    int32_t out=0; const int8_t *pa=a,*pb=b; int km1=(n>>4)-1;
    __asm__ volatile(
        "ee.zero.accx\n"
        "ee.vld.128.ip q0, %[pa], 16\n"
        "ee.vld.128.ip q1, %[pb], 16\n"
        "loopnez %[km1], 1f\n"
        "ee.vmulas.s8.accx.ld.ip q0, %[pa], 16, q0, q1\n"
        "ee.vld.128.ip q1, %[pb], 16\n"
        "1:\n"
        "ee.vmulas.s8.accx q0, q1\n"
        "ee.srs.accx %[out], %[sh], 0\n"
        : [out] "=&a"(out), [pa] "+&a"(pa), [pb] "+&a"(pb)
        : [km1] "a"(km1), [sh] "a"(0) : "memory");
    return out;
#else
    int32_t value=0;
    for(int i=0;i<n;i++) value+=(int32_t)a[i]*b[i];
    return value;
#endif
}
int ctc_kernel_selftest(void) {
    int8_t *a=alloc(2016),*b=alloc(2016);if(!a||!b) { free(a);free(b);return -1; }
    int sizes[]={16,128,288,1152,2016};int rc=0;
    for(int i=0;i<2016;i++) { a[i]=(i%255)-127;b[i]=((i*17)%255)-127; }
    for(int s=0;s<5;s++) {
        int32_t ref=0;for(int i=0;i<sizes[s];i++) ref+=(int32_t)a[i]*b[i];
        if(dot(a,b,sizes[s])!=ref) rc=-1;
    }
    free(a);free(b);return rc;
}
static int32_t nearest(float v) {
    // sanoTTS-jp's MIT-licensed saan_rint_i32 uses this same half-to-even instruction.
#if defined(ESP_PLATFORM) && defined(CONFIG_IDF_TARGET_ESP32S3)
    int32_t r;__asm__("round.s %0, %1, 0" : "=a"(r) : "f"(v));return r;
#else
    return (int32_t)lrintf(v);
#endif
}
static float quantize(const float *x,int8_t *q,int n,int stride,int fast) {
    float peak=1e-8f;
    for(int i=0;i<n;i++) if(fabsf(x[i])>peak) peak=fabsf(x[i]);
    float scale=peak/127;
    if(fast) {
        float inverse=127.0f/peak;
        for(int i=0;i<n;i++) { int32_t v=nearest(x[i]*inverse);if(v>127) v=127;if(v< -127) v=-127;q[i]=(int8_t)v; }
    } else for(int i=0;i<n;i++) q[i]=(int8_t)lrintf(x[i]/scale);
    for(int i=n;i<stride;i++) q[i]=0;
    return scale;
}
// Input time-major; convolution patches are channel-major [input channel][kernel].
static float *project(const Model *m,const float *x,int times,int channels,int kernel,int step,
                      const char *weight,const char *bias,int *out_times) {
    const Tensor *w=find(m,weight);
    int expected=H;
    if(!strcmp(weight,"encoder.conv2.weight")) expected=H*2;
    else if(strstr(weight,".mlp.fc1.weight")) expected=FF;
    else if(!strcmp(weight,"head.weight")) expected=m->vocab;
    if(!w || w->kind!=1 || w->rows!=(uint32_t)expected || w->cols!=(uint32_t)(channels*kernel)) return NULL;
    int rows=(int)w->rows, cols=(int)w->cols, stride=(int)w->stride;
    int nt=(times-kernel)/step+1;
    if(nt<=0) return NULL;
    const float *b=bias?vector(m,bias,rows):NULL;
    if(bias&&!b) return NULL;
    float *y=alloc((size_t)nt*rows*sizeof(float));
    float *patch=fast_alloc(cols*sizeof(float));
    const int tile=32;
    int8_t *qx=m->qa?fast_alloc((size_t)tile*stride):NULL;
    float *scales=m->qa?fast_alloc(tile*sizeof(float)):NULL;
    float *yt=m->qa?fast_alloc((size_t)tile*rows*sizeof(float)):NULL;
    if(!y||!patch||(m->qa&&(!qx||!scales||!yt))) goto fail;
    const int8_t *weights=(const int8_t *)(m->blob+w->data);
    const float *ws=(const float *)(m->blob+w->scale);
    if(m->qa) {
        for(int base=0;base<nt;base+=tile) {
          int length=nt-base;if(length>tile) length=tile;
          for(int t=0;t<length;t++) {
            for(int c=0;c<channels;c++) for(int k=0;k<kernel;k++) patch[c*kernel+k]=x[((base+t)*step+k)*channels+c];
            scales[t]=quantize(patch,qx+(size_t)t*stride,cols,stride,m->qa>=5);
          }
          // Activation tile stays in SRAM instead of rereading a >cache-sized PSRAM matrix per output row.
          for(int o=0;o<rows;o++) {
            for(int t=0;t<length;t++) yt[t*rows+o]=(float)dot(weights+(size_t)o*stride,qx+(size_t)t*stride,stride)*ws[o]*scales[t]+(b?b[o]:0);
#ifdef ESP_PLATFORM
            if((o&255)==0) cooperate();
#endif
          }
          memcpy(y+(size_t)base*rows,yt,(size_t)length*rows*sizeof(float));
        }
    } else {
        for(int t=0;t<nt;t++) {
            for(int c=0;c<channels;c++) for(int k=0;k<kernel;k++) patch[c*kernel+k]=x[(t*step+k)*channels+c];
            for(int o=0;o<rows;o++) {
                float v=0;
                for(int i=0;i<cols;i++) v+=patch[i]*weights[(size_t)o*stride+i];
                y[t*rows+o]=v*ws[o]+(b?b[o]:0);
            }
        }
    }
    free(patch); free(qx); free(scales); free(yt); *out_times=nt; return y;
fail:
    free(y); free(patch); free(qx); free(scales); free(yt); return NULL;
}
static float *linear(const Model *m,const float *x,int t,int c,const char *base,int bias) {
    char w[128],b[128]; snprintf(w,sizeof(w),"%s.weight",base); snprintf(b,sizeof(b),"%s.bias",base);
    int nt; return project(m,x,t,c,1,1,w,bias?b:NULL,&nt);
}
static int norm(const Model *m,float *x,int times,int channels,const char *name,int global) {
    char key[128]; snprintf(key,sizeof(key),"%s.weight",name);
    const float *weight=vector(m,key,channels);
    snprintf(key,sizeof(key),"%s.bias",name);
    const float *bias=global?vector(m,key,channels):NULL;
    if(!weight||(global&&!bias)) return -1;
    int groups=global?1:times, size=global?times*channels:channels;
    for(int g=0;g<groups;g++) {
        float *p=x+(size_t)g*size; double sum=0,sq=0;
        float mean;
        if(m->qa>=4 && !global) {
            float fs=0,fq=0;for(int i=0;i<size;i++) fs+=p[i];mean=fs/size;
            for(int i=0;i<size;i++) { float v=p[i]-mean;fq+=v*v; }sq=fq;
        } else {
            for(int i=0;i<size;i++) sum+=p[i];
            mean=(float)(sum/size);
            for(int i=0;i<size;i++) { double v=p[i]-mean; sq+=v*v; }
        }
        float inv=1.0f/sqrtf((float)(sq/size)+1e-5f);
        for(int i=0;i<size;i++) p[i]=(p[i]-mean)*inv*weight[i%channels]+(bias?bias[i%channels]:0);
    }
    return 0;
}
static void rope(float *x,int times) {
    for(int t=0;t<times;t++) for(int i=0;i<ROT;i+=2) {
        float angle=t/powf(10000.0f,(float)i/ROT),c=cosf(angle),s=sinf(angle);
      for(int h=0;h<HEADS;h++) {
        float *p=x+(size_t)t*H+h*HD+i,a=p[0],b=p[1];
        p[0]=a*c-b*s; p[1]=b*c+a*s;
      }
    }
}
static float *attention(const Model *m,const float *q,const float *k,const float *v,int times) {
    float *out=alloc((size_t)times*H*sizeof(float));
    float *scores=fast_alloc(times*sizeof(float));
    float *kh=fast_alloc((size_t)times*HD*sizeof(float)),*vh=fast_alloc((size_t)times*HD*sizeof(float));
    int ks=48,vs=(times+15)&~15;
    int8_t *kq=m->qa>=2?fast_alloc((size_t)times*ks):NULL;
    float *k_scale=m->qa>=2?fast_alloc(times*sizeof(float)):NULL;
    int8_t *vq=m->qa>=3?fast_alloc((size_t)HD*vs):NULL;
    int8_t *sq=m->qa>=3?fast_alloc(vs):NULL;
    float v_scale[HD];
    if(!out||!scores||!kh||!vh||(m->qa>=2&&(!kq||!k_scale))||(m->qa>=3&&(!vq||!sq))) {
        free(out);free(scores);free(kh);free(vh);free(kq);free(k_scale);free(vq);free(sq);return NULL;
    }
    for(int h=0;h<HEADS;h++) {
      for(int j=0;j<times;j++) for(int d=0;d<HD;d++) { kh[j*HD+d]=k[j*H+h*HD+d];vh[d*times+j]=v[j*H+h*HD+d]; }
      if(m->qa>=2) for(int j=0;j<times;j++) k_scale[j]=quantize(kh+j*HD,kq+j*ks,HD,ks,m->qa>=5);
      if(m->qa>=3) for(int d=0;d<HD;d++) v_scale[d]=quantize(vh+d*times,vq+d*vs,times,vs,m->qa>=5);
      for(int t=0;t<times;t++) {
        float query[HD],target[HD];
        for(int d=0;d<HD;d++) query[d]=q[t*H+h*HD+d];
        int8_t qq[48] __attribute__((aligned(16)));float qs=1;
        if(m->qa>=2) qs=quantize(query,qq,HD,ks,m->qa>=5);
        float peak=-INFINITY;
        for(int j=0;j<times;j++) {
            float sum=0;
            if(m->qa>=2) sum=(float)dot(qq,kq+j*ks,ks)*qs*k_scale[j];
            else for(int d=0;d<HD;d++) sum+=query[d]*kh[j*HD+d];
            scores[j]=sum/6.0f; if(scores[j]>peak) peak=scores[j];
        }
        float total=0;
        for(int j=0;j<times;j++) { scores[j]=m->qa>=4?fast_exp(scores[j]-peak):expf(scores[j]-peak); total+=scores[j]; }
        float score_scale=1;if(m->qa>=3) score_scale=quantize(scores,sq,times,vs,m->qa>=5);
        // Transposed values keep the reduction accumulator in an FPU register.
        // Summation order for each output is unchanged.
        for(int d=0;d<HD;d++) {
            float sum=0;
            if(m->qa>=3) sum=(float)dot(sq,vq+d*vs,vs)*score_scale*v_scale[d];
            else for(int j=0;j<times;j++) sum+=scores[j]*vh[d*times+j];
            target[d]=sum;
        }
        for(int d=0;d<HD;d++) out[t*H+h*HD+d]=target[d]/total;
#ifdef ESP_PLATFORM
        if((t&31)==0) cooperate();
#endif
      }
    }
    free(scores);free(kh);free(vh);free(kq);free(k_scale);free(vq);free(sq);return out;
}
static float *block(const Model *m,float *x,int times,int layer) {
    size_t bytes=(size_t)times*H*sizeof(float);
    float *z=alloc(bytes),*q=NULL,*k=NULL,*v=NULL,*a=NULL,*o=NULL,*mid=NULL;
    if(!z) return NULL;
    char name[96];
    memcpy(z,x,bytes); snprintf(name,sizeof(name),"encoder.layers.%d.input_layernorm",layer);
    if(norm(m,z,times,H,name,0)) goto fail;
    if(layer==0) ctc_progress("layer0_norm");
    snprintf(name,sizeof(name),"encoder.layers.%d.self_attn.q_proj",layer); q=linear(m,z,times,H,name,0);
    snprintf(name,sizeof(name),"encoder.layers.%d.self_attn.k_proj",layer); k=linear(m,z,times,H,name,0);
    snprintf(name,sizeof(name),"encoder.layers.%d.self_attn.v_proj",layer); v=linear(m,z,times,H,name,0);
    if(!q||!k||!v) goto fail;
    if(layer==0) ctc_progress("layer0_qkv");
    rope(q,times); rope(k,times);
    if(layer==0) ctc_progress("layer0_rope");
    a=attention(m,q,k,v,times);
    if(layer==0) ctc_progress("layer0_attention");
    free(q);q=NULL; free(k);k=NULL; free(v);v=NULL;
    if(!a) goto fail;
    snprintf(name,sizeof(name),"encoder.layers.%d.self_attn.o_proj",layer); o=linear(m,a,times,H,name,0);
    free(a);a=NULL; if(!o) goto fail;
    for(int i=0;i<times*H;i++) x[i]+=o[i];
    free(o);o=NULL; memcpy(z,x,bytes);
    snprintf(name,sizeof(name),"encoder.layers.%d.post_attention_layernorm",layer);
    if(norm(m,z,times,H,name,0)) goto fail;
    if(layer==0) ctc_progress("layer0_out_norm");
    snprintf(name,sizeof(name),"encoder.layers.%d.mlp.fc1",layer); mid=linear(m,z,times,H,name,1);
    if(!mid) goto fail;
    if(layer==0) ctc_progress("layer0_ff1");
    for(int i=0;i<times*FF;i++) mid[i]=m->qa>=4?fast_gelu(mid[i]):gelu(mid[i]);
    if(layer==0) ctc_progress("layer0_gelu");
    snprintf(name,sizeof(name),"encoder.layers.%d.mlp.fc2",layer); o=linear(m,mid,times,FF,name,1);
    if(!o) goto fail;
    for(int i=0;i<times*H;i++) x[i]+=o[i];
    free(z);free(mid);free(o);return x;
fail:
    free(z);free(q);free(k);free(v);free(a);free(o);free(mid);return NULL;
}
int ctc_run(const void *blob,size_t size,const float *audio,int samples,int qa,
            float **logits,int *frames,int *vocab) {
    if(!blob||!audio||!logits||!frames||!vocab||size<32||samples<1000||samples>288000) return -1;
    if(memcmp(blob,"RLCTC01\0",8)) return -2;
    const uint32_t *header=(const uint32_t *)blob;
    Model m={.blob=blob,.size=size,.count=header[2],.layers=header[3],.vocab=header[4],.qa=qa};
    if(qa>=4) init_math();
    if(m.count>128||m.layers<1||m.layers>6||m.vocab<2||m.vocab>128||32+(size_t)m.count*96>size) return -3;
    m.tensors=(const Tensor *)(m.blob+32);
    for(uint32_t i=0;i<m.count;i++) {
        const Tensor *t=m.tensors+i;
        if(!memchr(t->name,0,64)||!t->rows||!t->cols||t->rows>4096||t->cols>4096||t->kind>1||t->data%16||t->scale%16) return -4;
        size_t n=t->kind?(size_t)t->rows*t->stride:(size_t)t->rows*4;
        if(t->data>size||n>size-t->data) return -4;
        if(t->kind&&(t->stride<t->cols||t->stride%16||t->scale>size||(size_t)t->rows*4>size-t->scale)) return -4;
    }
    int t1,t2,t3;
    float *x=project(&m,audio,samples,1,127,64,"encoder.conv1.weight",NULL,&t1);
    float *y=NULL;
    if(!x) goto fail;
    for(int i=0;i<t1*H;i++) x[i]=qa>=4?fast_tanh(x[i]):tanhf(x[i]);
    if(norm(&m,x,t1,H,"encoder.groupnorm",1)) goto fail;
    ctc_progress("conv1");
    y=project(&m,x,t1,H,7,3,"encoder.conv2.weight","encoder.conv2.bias",&t2);
    free(x); x=y; if(!x) goto fail;
    for(int i=0;i<t2*H*2;i++) x[i]=qa>=4?fast_gelu(x[i]):gelu(x[i]);
    ctc_progress("conv2");
    y=project(&m,x,t2,H*2,3,2,"encoder.conv3.weight","encoder.conv3.bias",&t3);
    free(x);x=y;if(!x) goto fail;
    for(int i=0;i<t3*H;i++) x[i]=qa>=4?fast_gelu(x[i]):gelu(x[i]);
    ctc_progress("conv3");
    for(uint32_t layer=0;layer<m.layers;layer++) {
        if(!block(&m,x,t3,layer)) goto fail;
        char stage[24];snprintf(stage,sizeof(stage),"encoder_%lu",(unsigned long)layer);ctc_progress(stage);
#ifdef ESP_PLATFORM
        cooperate();
#endif
    }
    if(norm(&m,x,t3,H,"encoder.layer_norm",0)) goto fail;
    y=linear(&m,x,t3,H,"head",1); free(x);x=NULL;
    if(!y) goto fail;
    *logits=y; *frames=t3; *vocab=m.vocab; return 0;
fail:
    free(x);return -5;
}
