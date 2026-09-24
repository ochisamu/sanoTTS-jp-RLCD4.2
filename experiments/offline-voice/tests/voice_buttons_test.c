#include "voice_buttons.h"
#include <assert.h>
int main(void) {
    voice_buttons b;
    voice_buttons_reset(&b,0,0);
    assert(!voice_buttons_update(&b,0,40000));
    assert(!voice_buttons_update(&b,1,50000));
    assert(!voice_buttons_update(&b,1,90000));
    assert(!voice_buttons_update(&b,0,100000));
    assert(voice_buttons_update(&b,0,140000)==1);
    assert(!voice_buttons_update(&b,0,180000));
    assert(!voice_buttons_update(&b,2,200000));
    assert(!voice_buttons_update(&b,2,240000));
    assert(!voice_buttons_update(&b,0,250000));
    assert(voice_buttons_update(&b,0,290000)==2);
    // Held at startup/busy end does not fire when released.
    voice_buttons_reset(&b,2,0);
    assert(!voice_buttons_update(&b,2,50000));
    assert(!voice_buttons_update(&b,0,60000));
    assert(!voice_buttons_update(&b,0,100000));
    // Bounce shorter than 40 ms produces no action.
    assert(!voice_buttons_update(&b,1,110000));
    assert(!voice_buttons_update(&b,0,120000));
    assert(!voice_buttons_update(&b,0,160000));
    // A two-button chord is ignored until both are released.
    assert(!voice_buttons_update(&b,1,170000));
    assert(!voice_buttons_update(&b,1,210000));
    assert(!voice_buttons_update(&b,3,220000));
    assert(!voice_buttons_update(&b,2,230000));
    assert(!voice_buttons_update(&b,2,270000));
    assert(!voice_buttons_update(&b,0,280000));
    assert(!voice_buttons_update(&b,0,320000));
    return 0;
}
