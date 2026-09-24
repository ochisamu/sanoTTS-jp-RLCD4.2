#ifndef VOICE_BUTTONS_H
#define VOICE_BUTTONS_H
#include <stdint.h>
// Bits: KEY=1, BOOT=2. Release-triggered; held-at-boot/busy and chords ignored.
typedef struct { unsigned raw, stable, held; int ready; int64_t changed; } voice_buttons;
static inline void voice_buttons_reset(voice_buttons *b,unsigned mask,int64_t now) {
    *b=(voice_buttons){.raw=mask,.stable=mask,.changed=now};
}
static inline unsigned voice_buttons_update(voice_buttons *b,unsigned mask,int64_t now) {
    if(mask!=b->raw) {b->raw=mask;b->changed=now;}
    if(mask==3) {b->ready=0;b->held=0;}
    if(now-b->changed<40000) return 0;
    b->stable=mask;
    if(!b->ready) {if(!mask)b->ready=1;return 0;}
    if(mask) {b->held=mask;return 0;}
    unsigned event=b->held;b->held=0;return event;
}
#endif
