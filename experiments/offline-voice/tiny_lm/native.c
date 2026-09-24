#define _POSIX_C_SOURCE 200809L
#include "klm.h"
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <string.h>
static double now(void) {struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
int main(int argc,char **argv) {
    if(argc!=3) {fprintf(stderr,"usage: klm-native model.bin kana\n");return 2;}
    FILE *f=fopen(argv[1],"rb");if(!f)return 2;
    fseek(f,0,SEEK_END);long size=ftell(f);rewind(f);
    if(size<48 || size>4*1024*1024) {fclose(f);return 2;}
    void *blob=aligned_alloc(16,((size_t)size+15)&~(size_t)15);
    if(!blob || fread(blob,1,size,f)!=(size_t)size) {fclose(f);free(blob);return 2;}fclose(f);
    klm *m=klm_open(blob,size);if(!m || klm_kernel_selftest()) {fprintf(stderr,"invalid model/kernel\n");klm_close(m);free(blob);return 3;}
    int ids[82],n=klm_encode(m,argv[2],ids,82),token=-1,count=0;char answer[256]={0};
    if(n<0) {fprintf(stderr,"encode error %d\n",n);klm_close(m);free(blob);return 4;}
    double start=now();
    for(int i=0;i<n;i++) {token=klm_step(m,ids[i],NULL);if(token<0)break;}
    double first=now();
    while(token>=0 && token!=3 && count<40) {
        if(klm_append(m,token,answer,sizeof(answer)))break;
        count++;token=klm_step(m,token,NULL);
    }
    printf("%s\n",answer);
    fprintf(stderr,"tokens=%d prefill_ms=%.3f decode_ms=%.3f eos=%d workspace=%zu\n",count,(first-start)*1000,(now()-first)*1000,token==3,klm_workspace_bytes());
    klm_close(m);free(blob);return token==3?0:5;
}
