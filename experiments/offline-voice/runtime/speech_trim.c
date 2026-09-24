#include "speech_trim.h"
#include <math.h>
#include <stdlib.h>
#define WINDOW 320
#define MAX_WINDOWS 900
static int compare(const void *a,const void *b) {
    float x=*(const float*)a,y=*(const float*)b;return (x>y)-(x<y);
}
int speech_trim(const float *audio,int count,int *begin,int *end) {
    if(!audio||!begin||!end||count<WINDOW||count>MAX_WINDOWS*WINDOW) return 0;
    *begin=0;*end=count;
    float levels[MAX_WINDOWS],sorted[MAX_WINDOWS];int windows=count/WINDOW;
    for(int w=0;w<windows;w++) {
        float energy=0;for(int i=0;i<WINDOW;i++) { float x=audio[w*WINDOW+i];if(!isfinite(x)) return 0;energy+=x*x; }
        sorted[w]=levels[w]=sqrtf(energy/WINDOW);
    }
    qsort(sorted,windows,sizeof(float),compare);
    // Quietest fifth estimates the background; no fixed vocabulary or gap deletion.
    float threshold=fmaxf(40.0f/32768.0f,sorted[windows/5]*2.5f);
    int first=-1,last=-1,run=0;
    for(int w=0;w<windows;w++) {
        run=levels[w]>threshold?run+1:0;
        if(run>=3) { if(first<0) first=w-2;last=w; }
    }
    if(first<0) return 0;
    // Keep 250 ms of context on both ends, including unvoiced consonants.
    *begin=first*WINDOW-4000;if(*begin<0) *begin=0;
    *end=(last+1)*WINDOW+4000;if(*end>count) *end=count;
    // Preserve detection for very short words; pad to a one-second inference
    // window rather than misclassifying the utterance as no speech.
    if(*end-*begin<16000) {
        int missing=16000-(*end-*begin);
        *begin-=missing/2;if(*begin<0) *begin=0;
        *end=*begin+16000;
        if(*end>count) { *end=count;*begin=count>16000?count-16000:0; }
    }
    return 1;
}
