/* Original fixed-shape causal LM. W8A8 projections, FP32 attention/KV/RMSNorm.
 * PIE dot adapted from sanoTTS-jp (MIT, licenses/sanoTTS-jp-MIT.txt).
 * Not a GGUF/llama.cpp implementation. No network or dynamic executable model.
 */
#include "klm.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_heap_caps.h"
#endif
#ifndef KLM_LAYERS
#define KLM_LAYERS 4
#endif
#define L KLM_LAYERS
_Static_assert(L==4 || L==5,"unsupported KLM layers");
#ifndef KLM_DIM
#define KLM_DIM 192
#define KLM_HEADS 6
#define KLM_FF 512
#endif
#define D KLM_DIM
#define H KLM_HEADS
#define F KLM_FF
_Static_assert((D==192 && H==6 && F==512) || (D==256 && H==8 && F==768), "unsupported KLM shape");
#ifdef KLM_BPE
#define V 1024
#define T 96
#define TOKEN_STRIDE 40
_Static_assert(D==256 && H==8 && F==768, "unsupported BPE shape");
#else
#define V 128
#define T 128
#endif
#define HD (D/H)
typedef struct { const int8_t *w; const float *scale; int rows,cols; } Matrix;
typedef struct { const float *n1,*n2; Matrix qkv,o,up,down; } Block;
struct klm {
    const uint32_t *chars;
#ifdef KLM_BPE
    uint32_t single_chars[V];
    const uint8_t *tokens;
    const uint16_t *merges;
    int merge_count;
#endif
    Matrix emb;
    const float *pos,*norm;
    Block block[L];
    float *kv;
    float x[D],z[D],qkv[3*D],att[D],ff[F],logits[V],scores[T];
    _Alignas(16) int8_t quant[F];
    int position;
};
static void *alloc_mem(size_t n, int internal) {
    n=(n+15)&~(size_t)15;
#ifdef ESP_PLATFORM
    return heap_caps_aligned_alloc(16,n,(internal?MALLOC_CAP_INTERNAL:MALLOC_CAP_SPIRAM)|MALLOC_CAP_8BIT);
#else
    (void)internal;return aligned_alloc(16,n);
#endif
}
static int32_t dot(const int8_t *a,const int8_t *b,int n) {
#if defined(ESP_PLATFORM) && defined(CONFIG_IDF_TARGET_ESP32S3)
    int32_t out=0;const int8_t *pa=a,*pb=b;int km1=(n>>4)-1;
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
      : [out] "=&a"(out),[pa] "+&a"(pa),[pb] "+&a"(pb)
      : [km1] "a"(km1),[sh] "a"(0):"memory");
    return out;
#else
    int32_t sum=0;for(int i=0;i<n;i++) sum+=(int32_t)a[i]*b[i];return sum;
#endif
}
int klm_kernel_selftest(void) {
    _Alignas(16) int8_t a[F],b[F];
    for(int i=0;i<F;i++) {a[i]=i%255-127;b[i]=(i*17)%255-127;}
    int sizes[]={16,D,F};
    for(int j=0;j<3;j++) {
        int32_t ref=0;for(int i=0;i<sizes[j];i++)ref+=(int32_t)a[i]*b[i];
        if(dot(a,b,sizes[j])!=ref)return -1;
    }
    return 0;
}
typedef struct {const uint8_t *base;size_t size,offset;int bad;} Reader;
static const void *take(Reader *r,size_t n) {
    size_t off=(r->offset+15)&~(size_t)15;
    if(off>r->size || n>r->size-off) {r->bad=1;return NULL;}
    r->offset=off+n;return r->base+off;
}
static const float *floats(Reader *r,size_t n) {
    const float *p=take(r,n*4);
    if(p)for(size_t i=0;i<n;i++)if(!isfinite(p[i]))r->bad=1;
    return p;
}
static Matrix matrix(Reader *r,int rows,int cols) {
    Matrix m={.w=take(r,(size_t)rows*cols),.scale=floats(r,rows),.rows=rows,.cols=cols};
    if(m.scale)for(int i=0;i<rows;i++)if(m.scale[i]<=0)r->bad=1;
    return m;
}
size_t klm_workspace_bytes(void) {return sizeof(klm)+(size_t)2*L*T*D*4;}
klm *klm_open(const void *blob,size_t bytes) {
    if(!blob || ((uintptr_t)blob&15) || bytes<48)return NULL;
    const uint8_t *b=blob;const uint32_t *h=(const uint32_t*)(b+8);
#ifdef KLM_BPE
    if(memcmp(b,"KLMW8v2\0",8) || h[8]!=918 || h[9]!=TOKEN_STRIDE)return NULL;
#else
    if(memcmp(b,"KLMW8v1\0",8) || h[8] || h[9])return NULL;
#endif
    if(h[0]!=bytes || h[1]!=L || h[2]!=D || h[3]!=H || h[4]!=F || h[5]!=V || h[6]!=T)return NULL;
    uint32_t hash=2166136261u;for(size_t i=48;i<bytes;i++)hash=(hash^b[i])*16777619u;
    if(hash!=h[7])return NULL;
    klm *m=alloc_mem(sizeof(*m),1);if(!m)return NULL;
    memset(m,0,sizeof(*m));Reader r={.base=b,.size=bytes,.offset=48};
#ifdef KLM_BPE
    m->tokens=take(&r,V*TOKEN_STRIDE);m->merge_count=(int)h[8];m->merges=take(&r,h[8]*6);
    m->chars=m->single_chars;
#else
    m->chars=take(&r,4*V);
#endif
    m->emb=matrix(&r,V,D);m->pos=floats(&r,T*D);
    for(int l=0;l<L;l++) {
        Block *p=&m->block[l];p->n1=floats(&r,D);p->qkv=matrix(&r,3*D,D);p->o=matrix(&r,D,D);
        p->n2=floats(&r,D);p->up=matrix(&r,F,D);p->down=matrix(&r,D,F);
    }
    m->norm=floats(&r,D);
    if(r.bad || r.offset!=bytes) {klm_close(m);return NULL;}
#ifdef KLM_BPE
    /* Constrain token bytes to the same kana/digit alphabet as v1. */
    for(int i=0;i<V;i++) {
        const uint8_t *row=m->tokens+i*TOKEN_STRIDE;int len=row[0],at=1,count=0;uint32_t single=0;
        if(len>36 || (i<5?len!=0:len==0)) {klm_close(m);return NULL;}
        while(at<=len) {
            uint32_t cp=row[at++];
            if(cp>=0xe0 && cp<=0xef && at+1<=len && (row[at]&0xc0)==0x80 && (row[at+1]&0xc0)==0x80) {
                cp=((cp&15)<<12)|((row[at]&63)<<6)|(row[at+1]&63);at+=2;
                if(cp<0x800) {klm_close(m);return NULL;}
            } else if(cp>=128) {klm_close(m);return NULL;}
            if(!((cp>=0x3041 && cp<=0x3096) || cp==0x30fc || cp==0x3002 || cp==0x3001 || cp==0xff01 || cp==0xff1f || (cp>='0' && cp<='9'))) {klm_close(m);return NULL;}
            single=cp;count++;
        }
        for(int j=len+1;j<TOKEN_STRIDE;j++)if(row[j]) {klm_close(m);return NULL;}
        if(count>12) {klm_close(m);return NULL;}
        if(count==1)m->single_chars[i]=single;
        if(i>=5 && i<106 && count!=1) {klm_close(m);return NULL;}
        if(i>=106 && count<2) {klm_close(m);return NULL;}
        if(i>=5 && i<106)for(int j=5;j<i;j++)if(m->single_chars[j]==single) {klm_close(m);return NULL;}
    }
    for(int i=0;i<m->merge_count;i++) {
        int left=m->merges[3*i],right=m->merges[3*i+1],out=m->merges[3*i+2];
        if(out!=106+i || left<5 || right<5 || left>=out || right>=out) {klm_close(m);return NULL;}
        const uint8_t *a=m->tokens+left*TOKEN_STRIDE,*c=m->tokens+right*TOKEN_STRIDE,*o=m->tokens+out*TOKEN_STRIDE;
        if(a[0]+c[0]!=o[0] || memcmp(o+1,a+1,a[0]) || memcmp(o+1+a[0],c+1,c[0])) {klm_close(m);return NULL;}
    }
#else
    /* Validate the fixed vocabulary, not arbitrary code points from flash. */
    for(int i=0;i<5;i++)if(m->chars[i]) {klm_close(m);return NULL;}
    for(int i=5;i<91;i++)if(m->chars[i]!=(uint32_t)(0x3041+i-5)) {klm_close(m);return NULL;}
    const uint32_t tail[]={0x30fc,0x3002,0x3001,0xff01,0xff1f,'0','1','2','3','4','5','6','7','8','9'};
    for(int i=91;i<V;i++)if(m->chars[i]!=(i<106?tail[i-91]:0)) {klm_close(m);return NULL;}
#endif
    m->kv=alloc_mem((size_t)2*L*T*D*4,0);
    if(!m->kv) {klm_close(m);return NULL;}
    return m;
}
void klm_close(klm *m) {if(m) {free(m->kv);free(m);}}
void klm_reset(klm *m) {if(m)m->position=0;}
static void norm(float *out,const float *in,const float *w) {
    float square=0;for(int i=0;i<D;i++)square+=in[i]*in[i];
    float gain=1/sqrtf(square/D+1e-5f);
    for(int i=0;i<D;i++)out[i]=in[i]*gain*w[i];
}
static void linear(klm *m,float *out,const float *in,const Matrix *w) {
    float peak=1e-8f;for(int i=0;i<w->cols;i++)if(fabsf(in[i])>peak)peak=fabsf(in[i]);
    float inv=127/peak,scale=peak/127;
    for(int i=0;i<w->cols;i++) {
        int q=(int)lrintf(in[i]*inv);if(q>127)q=127;if(q< -127)q=-127;m->quant[i]=(int8_t)q;
    }
    for(int o=0;o<w->rows;o++)out[o]=(float)dot(w->w+(size_t)o*w->cols,m->quant,w->cols)*scale*w->scale[o];
}
int klm_step(klm *m,int token,float *logits) {
    if(!m || token<0 || token>=V || m->position>=T)return -1;
    int p=m->position;
    for(int i=0;i<D;i++)m->x[i]=m->emb.w[token*D+i]*m->emb.scale[token]+m->pos[p*D+i];
    for(int l=0;l<L;l++) {
        Block *b=&m->block[l];norm(m->z,m->x,b->n1);linear(m,m->qkv,m->z,&b->qkv);
        float *k=m->kv+(size_t)(2*l)*T*D,*v=k+T*D;
        memcpy(k+p*D,m->qkv+D,D*4);memcpy(v+p*D,m->qkv+2*D,D*4);
        for(int h=0;h<H;h++) {
            float max=-INFINITY;
            for(int t=0;t<=p;t++) {
                float s=0;for(int i=0;i<HD;i++)s+=m->qkv[h*HD+i]*k[t*D+h*HD+i];
                m->scores[t]=s/sqrtf((float)HD);if(m->scores[t]>max)max=m->scores[t];
            }
            float sum=0;for(int t=0;t<=p;t++) {m->scores[t]=expf(m->scores[t]-max);sum+=m->scores[t];}
            for(int i=0;i<HD;i++) {float s=0;for(int t=0;t<=p;t++)s+=m->scores[t]*v[t*D+h*HD+i];m->att[h*HD+i]=s/sum;}
        }
        linear(m,m->z,m->att,&b->o);for(int i=0;i<D;i++)m->x[i]+=m->z[i];
        norm(m->z,m->x,b->n2);linear(m,m->ff,m->z,&b->up);
        for(int i=0;i<F;i++)if(m->ff[i]<0)m->ff[i]=0;
        linear(m,m->z,m->ff,&b->down);for(int i=0;i<D;i++)m->x[i]+=m->z[i];
    }
    norm(m->z,m->x,m->norm);linear(m,m->logits,m->z,&m->emb);m->position++;
    if(logits)memcpy(logits,m->logits,sizeof(m->logits));
    int best=3;
    for(int i=3;i<V;i++) {
        if(!isfinite(m->logits[i]))return -2;
#ifdef KLM_BPE
        int valid=i==3 || (i>=5 && m->tokens[i*TOKEN_STRIDE]);
#else
        int valid=i==3 || m->chars[i];
#endif
        if(i!=4 && valid && m->logits[i]>m->logits[best])best=i;
    }
    return best;
}
int klm_encode(const klm *m,const char *text,int *ids,int capacity) {
    if(!m || !text || !ids || capacity<3)return -1;
    const unsigned char *p=(const unsigned char*)text;int n=0;ids[n++]=1;
    while(*p) {
        uint32_t cp=*p++;
        if(cp<128) {if(cp==' ' || cp=='\t')continue;if(cp=='?')cp=0xff1f;if(cp=='!')cp=0xff01;}
        else if(cp>=0xe0 && cp<=0xef) {
            if(!p[0] || !p[1] || (p[0]&0xc0)!=0x80 || (p[1]&0xc0)!=0x80)return -2;
            cp=((cp&15)<<12)|((p[0]&63)<<6)|(p[1]&63);p+=2;
            if(cp<0x800 || (cp>=0xd800 && cp<=0xdfff))return -2;
        } else return -2;
        if(cp==0x3000)continue;
        if(cp>=0x30a1 && cp<=0x30f6)cp-=0x60;
        int id=-1;for(int i=5;i<V;i++)if(cp==m->chars[i]) {id=i;break;}
        if(id<0)return -3; /* no silent UNK substitution */
        if(n>=capacity-1)return -4;
        ids[n++]=id;
    }
    if(n==1)return -5;
#ifdef KLM_BPE
    /* Lowest-rank available pair, leftmost on ties: matches tokenizers BPE. */
    for(;;) {
        int rank=m->merge_count,where=-1;
        for(int pos=1;pos<n-1;pos++)for(int j=0;j<rank;j++) {
            if(ids[pos]==m->merges[3*j] && ids[pos+1]==m->merges[3*j+1]) {rank=j;where=pos;break;}
        }
        if(where<0)break;
        ids[where]=m->merges[3*rank+2];
        memmove(ids+where+1,ids+where+2,(size_t)(n-where-2)*sizeof(*ids));n--;
    }
#endif
    ids[n++]=2;return n;
}
int klm_append(const klm *m,int token,char *out,size_t capacity) {
#ifdef KLM_BPE
    if(!m || token<5 || token>=V || !out)return -1;
    const uint8_t *row=m->tokens+token*TOKEN_STRIDE;size_t n=strlen(out),need=row[0];
    if(!need || n+need>=capacity)return -1;
    memcpy(out+n,row+1,need);out[n+need]=0;return 0;
#else
    if(!m || token<5 || token>=V || !m->chars[token] || !out)return -1;
    uint32_t cp=m->chars[token];size_t n=strlen(out),need=cp<128?1:3;
    if(n+need>=capacity)return -1;
    if(need==1)out[n++]=(char)cp;
    else {out[n++]=(char)(0xe0|(cp>>12));out[n++]=(char)(0x80|((cp>>6)&63));out[n++]=(char)(0x80|(cp&63));}
    out[n]=0;return 0;
#endif
}

int klm_tts_text(const char *text,char *out,size_t capacity) {
    if(!text || !out || !capacity)return -1;
    size_t n=0;out[0]=0;
    while(*text) {
        char mark=0;size_t consumed=1;
        if(!strncmp(text,"。",3) || !strncmp(text,"、",3) || !strncmp(text,"！",3)) {mark='#';consumed=3;}
        else if(!strncmp(text,"？",3)) {mark='?';consumed=3;}
        if(n+1>=capacity) {out[0]=0;return -1;}
        out[n++]=mark?mark:*text;text+=consumed;
    }
    out[n]=0;return (int)n;
}
