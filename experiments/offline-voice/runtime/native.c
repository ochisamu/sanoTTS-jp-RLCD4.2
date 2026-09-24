#include "ctc_runtime.h"
#include <stdio.h>
#include <stdlib.h>
static void *readfile(const char *name,size_t *size) {
    FILE *f=fopen(name,"rb"); if(!f) return NULL;
    fseek(f,0,SEEK_END); long n=ftell(f); rewind(f);
    if(n<=0) { fclose(f);return NULL; }
    void *p=aligned_alloc(16,((size_t)n+15)&~(size_t)15);
    if(!p||fread(p,1,n,f)!=(size_t)n) { free(p); fclose(f);return NULL; }
    fclose(f);*size=n;return p;
}
int main(int argc,char **argv) {
    if(ctc_kernel_selftest()) return 5;
    if(argc!=5) { fprintf(stderr,"model.bin input.f32 logits.f32 quantize_activations(0/1)\n");return 1; }
    size_t model_size=0,audio_size=0;
    void *model=readfile(argv[1],&model_size),*audio=readfile(argv[2],&audio_size);
    float *logits=NULL;int frames=0,vocab=0;
    int rc=ctc_run(model,model_size,audio,audio_size/4,atoi(argv[4]),&logits,&frames,&vocab);
    if(rc) { fprintf(stderr,"ctc_run failed %d\n",rc);free(model);free(audio);return 2; }
    FILE *f=fopen(argv[3],"wb");if(!f) return 3;
    size_t count=(size_t)frames*vocab;
    if(fwrite(logits,sizeof(float),count,f)!=count) return 4;
    fclose(f);printf("frames=%d vocab=%d\n",frames,vocab);
    ctc_free(logits);free(model);free(audio);return 0;
}
