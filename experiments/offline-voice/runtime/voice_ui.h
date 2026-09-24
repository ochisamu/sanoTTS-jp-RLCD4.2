#ifndef VOICE_UI_H
#define VOICE_UI_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define VOICE_UI_BYTES 15000
typedef struct {
    char heard[1024], spoken[1024], status[48], battery[24];
    bool reply, captions;
    unsigned page;
} voice_ui;
// All routines are allocation-free. Framebuffer uses ST7305 landscape packing.
void voice_ui_copy(char *dst,size_t capacity,const char *src);
unsigned voice_ui_pages(const char *text);
bool voice_ui_has_glyph(uint32_t code);
void voice_ui_draw(uint8_t *fb,const voice_ui *ui);
void voice_ui_mouth(uint8_t *fb,uint8_t level,bool speaking);
#endif
