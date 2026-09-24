/* SPDX-License-Identifier: Apache-2.0
 * Copyright 2026 ochisamu
 * Copyright 2026 masa
 *
 * C/float adaptation of CharaDock AtomEchoPcmProcessor (Apache-2.0).
 * Changes: fixed 22.05 kHz, static 8 ms tail, no heap, finite-state guards,
 * explicit legacy comparison mode. See licenses/NOTICE-CharaDock.txt.
 */
#include "echo_dsp.h"
#include <math.h>
#include <string.h>

#define PI_F 3.14159265358979323846f
static float db_linear(float db) { return powf(10.0f, db / 20.0f); }

static void biquad(echo_biquad *f, bool highpass, float hz, float q, float db)
{
    float w = 2 * PI_F * hz / ECHO_DSP_RATE;
    float c = cosf(w), alpha = sinf(w) / (2 * q);
    float a0, a1 = -2 * c, a2, b0, b1, b2;
    if (highpass) {
        b0 = (1 + c) / 2; b1 = -(1 + c); b2 = b0;
        a0 = 1 + alpha; a2 = 1 - alpha;
    } else {
        float a = powf(10.0f, db / 40.0f);
        b0 = 1 + alpha * a; b1 = -2 * c; b2 = 1 - alpha * a;
        a0 = 1 + alpha / a; a2 = 1 - alpha / a;
    }
    *f = (echo_biquad){b0/a0, b1/a0, b2/a0, a1/a0, a2/a0, 0, 0};
}

bool echo_dsp_init(echo_dsp *s, bool tuned, float output_gain)
{
    if (!s) return false;
    memset(s, 0, sizeof(*s));
    if (!isfinite(output_gain) || output_gain < .5f || output_gain > 1.5f) {
        s->finished = true;
        return false;
    }
    s->tuned = tuned; s->output_gain = output_gain;
    biquad(&s->filters[0], true, 240, .5411961f, 0);
    biquad(&s->filters[1], true, 240, 1.306563f, 0);
    biquad(&s->filters[2], false, 550, 1, -3);
    biquad(&s->filters[3], false, 2600, .9f, 3);
    s->attack = expf(-1 / (.015f * ECHO_DSP_RATE));
    s->release = expf(-1 / (.120f * ECHO_DSP_RATE));
    return true;
}

static float filter(echo_biquad *f, float x)
{
    float y = f->b0*x + f->z1;
    f->z1 = f->b1*x - f->a1*y + f->z2;
    f->z2 = f->b2*x - f->a2*y;
    return y;
}

bool echo_dsp_init_rlcd_legacy(echo_dsp *s)
{
    if(!echo_dsp_init(s,true,1.2f)) return false;
    biquad(&s->filters[0],true,300,.5411961f,0);
    biquad(&s->filters[1],true,300,1.306563f,0);
    biquad(&s->filters[2],false,550,1,-4);
    biquad(&s->filters[3],false,2600,.9f,5);
    return true;
}

bool echo_dsp_init_rlcd(echo_dsp *s)
{
    if(!echo_dsp_init_rlcd_legacy(s))return false;
    // Clearer speech trial: remove boxy lower mids, move presence toward
    // consonants. No added broadband gain; keep the 0.7 limiter and volume.
    biquad(&s->filters[2],false,650,.8f,-6);
    biquad(&s->filters[3],false,3300,.8f,5);
    return true;
}

static int16_t quantize(float x)
{
    x = fmaxf(-1, fminf(1, x));
    return (int16_t)floorf(x * 32767 + .5f); /* JavaScript Math.round */
}

static int16_t shape(echo_dsp *s, int16_t input)
{
    if (!s->tuned) return (int16_t)(input * .25f);
    float x = (input / 32768.0f) * .5f;
    for (int i = 0; i < 4; ++i) x = filter(&s->filters[i], x);
    float level = fabsf(x);
    float coefficient = level > s->envelope ? s->attack : s->release;
    s->envelope = coefficient*s->envelope + (1-coefficient)*level;
    float db = 20 * log10f(fmaxf(1e-8f, s->envelope));
    float compressed = db;
    if (db > -25 && db < -19) { /* -22 dB threshold, 6 dB soft knee */
        float position = db + 25;
        compressed += (1/2.5f - 1) * position*position / 12;
    } else if (db >= -19) {
        compressed = -22 + (db + 22)/2.5f;
    }
    x *= db_linear(compressed - db + 12) * s->output_gain;
    float magnitude = fabsf(x);
    if (magnitude > .58f) {
        float p = fminf(1, (magnitude - .58f)/.42f);
        float curve = (1 - expf(-4*p))/(1 - expf(-4));
        x = copysignf(fminf(.7f, .58f + .12f*curve), x);
    }
    x = fmaxf(-.7f, fminf(.7f, x));
    if (s->seen < ECHO_DSP_FADE) x *= (s->seen + 1.0f)/ECHO_DSP_FADE;
    ++s->seen;
    if (!isfinite(x) || !isfinite(s->envelope)) {
        ++s->faults;
        for (int i = 0; i < 4; ++i) s->filters[i].z1 = s->filters[i].z2 = 0;
        s->envelope = 0;
        return 0;
    }
    return quantize(x);
}

size_t echo_dsp_push(echo_dsp *s, const int16_t *input, size_t count, int16_t *output)
{
    if (!s || !input || !output || s->finished) return 0;
    size_t written = 0;
    for (size_t i = 0; i < count; ++i) {
        int16_t sample = shape(s, input[i]);
        if (!s->tuned) { output[written++] = sample; continue; }
        if (s->pending == ECHO_DSP_FADE) {
            output[written++] = s->tail[s->head];
            s->tail[s->head] = sample;
            s->head = (s->head + 1) % ECHO_DSP_FADE;
        } else {
            s->tail[(s->head + s->pending) % ECHO_DSP_FADE] = sample;
            ++s->pending;
        }
    }
    return written;
}

size_t echo_dsp_finish(echo_dsp *s, int16_t *output)
{
    if (!s || !output || s->finished) return 0;
    size_t n = s->pending;
    for (size_t i = 0; i < n; ++i) {
        float fade = n > 1 ? (float)(n-i-1)/(n-1) : 0;
        output[i] = (int16_t)floorf(s->tail[(s->head+i)%ECHO_DSP_FADE]*fade + .5f);
    }
    s->pending = 0; s->finished = true;
    return n;
}
