#include "phonemes.h"
#include "kana_table.h"
#include <string.h>
int phonemes_to_kana(const int *ids,int count,char *output,size_t capacity) {
    if(!ids||!output||capacity<1||count<0) return -1;
    size_t used=0;int dropped=0;output[0]=0;
    for(int i=0;i<count;i++) {
        int p=ids[i];if(p<1||p>=41) return -1;
        const char *text=kana_map[p][5];
        if(!*text && i+1<count && ids[i+1]>=1 && ids[i+1]<=5) {
            text=kana_map[p][ids[i+1]-1];if(*text) i++;
        }
        if(!*text) { dropped++;continue; }
        size_t n=strlen(text);if(used+n>=capacity) return -1;
        memcpy(output+used,text,n);used+=n;output[used]=0;
    }
    return dropped;
}
