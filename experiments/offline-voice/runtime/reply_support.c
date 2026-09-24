#include "reply_support.h"
#include "reply_assets.h"
#include <string.h>

/* Bounded UTF-8 byte copy; only removes complete known punctuation sequences.
 * This is deliberately NOT substring or approximate matching: e.g. "1+2"
 * must never retrieve the answer for "1+1". Unknown questions go to the LM.
 */
static int normalized(const char *s,char *out,size_t capacity) {
    size_t n=0;
    if(!s||!out||!capacity)return 0;
    while(*s) {
        size_t skip=0;
        if(*s==' '||*s=='\t'||*s=='?'||*s=='!'||*s=='.'||*s==',')skip=1;
        else if(!strncmp(s,"。",3)||!strncmp(s,"、",3)||!strncmp(s,"？",3)||!strncmp(s,"！",3))skip=3;
        if(skip){s+=skip;continue;}
        if(n+1>=capacity){out[0]=0;return 0;}
        out[n++]=*s++;
    }
    out[n]=0;return n>0;
}
int reply_knowledge_lookup(const char *question,reply_fact *out) {
    char query[256],candidate[256];
    if(!out)return 0;
    memset(out,0,sizeof(*out));
    if(!normalized(question,query,sizeof(query)))return 0;
    const char *q=query;
    const char *prefixes[]={"ねえ","あのね","ちょっときいて"};
    for(size_t i=0;i<sizeof(prefixes)/sizeof(*prefixes);i++)
        if(!strncmp(q,prefixes[i],strlen(prefixes[i]))){q+=strlen(prefixes[i]);break;}
    for(size_t i=0;i<sizeof(reply_knowledge)/sizeof(*reply_knowledge);i++) {
        const kb_row *r=&reply_knowledge[i];
        if(normalized(r->query,candidate,sizeof(candidate))&&!strcmp(q,candidate)) {
            out->id=r->id;out->reading=r->reading;out->display=r->display;return 1;
        }
    }
    return 0;
}
const char *reply_display_text(const char *reading) {
    char clean[256];
    if(!normalized(reading,clean,sizeof(clean)))return reading;
    for(size_t i=0;i<sizeof(reply_captions)/sizeof(*reply_captions);i++)
        if(!strcmp(clean,reply_captions[i].reading))return reply_captions[i].display;
    return reading;
}
