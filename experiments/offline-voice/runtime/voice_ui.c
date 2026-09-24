// SPDX-License-Identifier: MIT
// Original geometric face, not a copy of Stack-chan artwork or software.
#include "voice_ui.h"
#include "shinonome16.h"
#include <stdio.h>
#include <string.h>

static uint32_t next(const char **p) {
    const unsigned char *s=(const unsigned char *)*p;
    if(!*s)return 0;
    uint32_t cp;int n;
    if(s[0]<128){*p+=1;return s[0];}
    if(s[0]>=0xc2 && s[0]<=0xdf){cp=s[0]&31;n=2;}
    else if(s[0]>=0xe0 && s[0]<=0xef){cp=s[0]&15;n=3;}
    else if(s[0]>=0xf0 && s[0]<=0xf4){cp=s[0]&7;n=4;}
    else {*p+=1;return 0xfffd;}
    for(int i=1;i<n;i++) {
        if(!s[i] || (s[i]&0xc0)!=0x80){*p+=1;return 0xfffd;}
        cp=(cp<<6)|(s[i]&63);
    }
    *p+=n;
    if((n==2 && cp<128)||(n==3 && cp<2048)||(n==4 && cp<65536)||
       cp>0x10ffff||(cp>=0xd800 && cp<=0xdfff))return 0xfffd;
    return cp;
}
void voice_ui_copy(char *dst,size_t capacity,const char *src) {
    if(!dst || !capacity)return;
    dst[0]=0;if(!src)return;
    size_t used=0;
    while(*src) {
        const char *begin=src;next(&src);size_t n=(size_t)(src-begin);
        if(used+n>=capacity)break;
        memcpy(dst+used,begin,n);used+=n;
    }
    dst[used]=0;
}
static const jp_glyph *lookup(uint32_t cp) {
    size_t a=0,b=sizeof(jp_font)/sizeof(jp_font[0]);
    while(a<b){size_t m=(a+b)/2;if(jp_font[m].code<cp)a=m+1;else b=m;}
    return a<sizeof(jp_font)/sizeof(jp_font[0]) && jp_font[a].code==cp?jp_font+a:NULL;
}
bool voice_ui_has_glyph(uint32_t cp){return lookup(cp)!=NULL;}
static int width(uint32_t cp){const jp_glyph *g=lookup(cp);return g?g->width:16;}
static void pixel(uint8_t *fb,int x,int y,bool black) {
    if((unsigned)x>=400 || (unsigned)y>=300)return;
    int iy=299-y;size_t i=(size_t)(x>>1)*75+(iy>>2);
    uint8_t mask=(uint8_t)(1u<<(7-(((iy&3)<<1)|(x&1))));
    if(black)fb[i]&=(uint8_t)~mask;else fb[i]|=mask;
}
static void rect(uint8_t *fb,int x,int y,int w,int h,bool black) {
    for(int j=0;j<h;j++)for(int i=0;i<w;i++)pixel(fb,x+i,y+j,black);
}
static void letter(uint8_t *fb,int x,int y,uint32_t cp) {
    const jp_glyph *g=lookup(cp);
    if(!g){rect(fb,x+1,y+1,13,1,true);rect(fb,x+1,y+14,13,1,true);
        rect(fb,x+1,y+1,1,14,true);rect(fb,x+13,y+1,1,14,true);return;}
    for(int j=0;j<16;j++)for(int i=0;i<g->width;i++)if(g->rows[j]&(0x8000u>>i))pixel(fb,x+i,y+j,true);
}
static void text(uint8_t *fb,int x,int y,int limit,const char *s) {
    while(*s){uint32_t cp=next(&s);int w=width(cp);if(x+w>limit)break;letter(fb,x,y,cp);x+=w;}
}
static void big_text(uint8_t *fb,int y,const char *s) {
    int w=0;const char *p=s;while(*p)w+=width(next(&p))*2;
    int x=(400-w)/2;if(x<8)x=8;
    while(*s){uint32_t cp=next(&s);const jp_glyph *g=lookup(cp);if(!g)continue;
        if(x+g->width*2>392)break;
        for(int j=0;j<16;j++)for(int i=0;i<g->width;i++)if(g->rows[j]&(0x8000u>>i))rect(fb,x+i*2,y+j*2,2,2,true);
        x+=g->width*2;
    }
}
static const char *page_end(const char *s,uint8_t *fb,int y) {
    int x=12,row=0;
    while(*s) {
        const char *start=s;uint32_t cp=next(&s);
        if(cp=='\n'){x=12;if(++row==3)return s;continue;}
        if(cp=='\r')continue;
        int w=width(cp);
        if(x+w>388){x=12;if(++row==3)return start;}
        if(fb)letter(fb,x,y+row*18,cp);
        x+=w;
    }
    return s;
}
unsigned voice_ui_pages(const char *s) {
    unsigned count=0;if(!s || !*s)return 1;
    while(*s){s=page_end(s,NULL,0);count++;}return count;
}
static void box(uint8_t *fb,int y,const char *label,const char *s,unsigned page) {
    char number[24];unsigned count=voice_ui_pages(s),selected=page%count;
    text(fb,12,y,270,label);
    snprintf(number,sizeof(number),"%u/%u",selected+1,count);text(fb,340,y,388,number);
    rect(fb,12,y+18,376,1,true);
    for(unsigned i=0;i<selected;i++)s=page_end(s,NULL,0);
    if(*s)page_end(s,fb,y+22);else text(fb,12,y+22,388,"まだありません");
}
void voice_ui_mouth(uint8_t *fb,uint8_t level,bool speaking) {
    rect(fb,137,148,126,51,false);
    if(speaking) {
        int h=10+level*30/255;rect(fb,168,153,64,h,true);
        if(h>12)rect(fb,176,159,48,h-10,false);
    } else {
        rect(fb,151,157,7,8,true);rect(fb,242,157,7,8,true);
        rect(fb,158,165,84,6,true);
    }
}
static const char *status(const char *s) {
    if(strstr(s,"LISTEN"))return "LISTENING";
    if(strstr(s,"RECOGNIZ"))return "RECOGNIZING";
    if(strstr(s,"THINKING"))return "THINKING";
    if(strstr(s,"SYNTHESIZ"))return "SYNTHESIZING";
    if(strstr(s,"SPEAKING"))return "SPEAKING";
    if(strstr(s,"READY"))return "READY";
    if(strstr(s,"START"))return "STARTING";
    if(strstr(s,"QUIET")||strstr(s,"NO SPEECH"))return "NO SPEECH / TRY AGAIN";
    return s;
}
void voice_ui_draw(uint8_t *fb,const voice_ui *ui) {
    memset(fb,255,VOICE_UI_BYTES);
    text(fb,12,6,220,ui->reply?"CHAT / EXPERIMENTAL":"ECHO MODE");
    text(fb,260,6,396,ui->battery);
    rect(fb,12,27,376,1,true);
    big_text(fb,38,status(ui->status));
    // Larger original face; its animation area never touches the subtitles.
    rect(fb,91,91,34,46,true);rect(fb,275,91,34,46,true);
    rect(fb,95,95,8,10,false);rect(fb,279,95,8,10,false);
    for(int i=0;i<3;i++){rect(fb,65+i*6,143,2,10,true);rect(fb,321+i*6,143,2,10,true);}
    voice_ui_mouth(fb,0,strstr(ui->status,"SPEAKING")!=NULL);
    if(ui->captions && (ui->spoken[0] || ui->heard[0])) {
        box(fb,204,ui->spoken[0]?"REPLY":"HEARD",ui->spoken[0]?ui->spoken:ui->heard,ui->page);
    } else {
        text(fb,96,229,394,strstr(ui->status,"READY")?"PRESS / RELEASE TO TALK":"PLEASE WAIT");
        rect(fb,12,274,376,1,true);
        text(fb,12,281,398,"KEY: ECHO       BOOT: CHAT");
    }
}
