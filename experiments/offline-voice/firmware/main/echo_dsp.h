/* SPDX-License-Identifier: Apache-2.0
 * Copyright 2026 ochisamu
 * Adapted from CharaDock; see licenses/NOTICE-CharaDock.txt.
 */
#ifndef ECHO_DSP_H
#define ECHO_DSP_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ECHO_DSP_RATE 22050
#define ECHO_DSP_FADE 176 /* round(22050 * 8 / 1000), as in CharaDock */

typedef struct { float b0, b1, b2, a1, a2, z1, z2; } echo_biquad;
typedef struct {
    echo_biquad filters[4];
    float envelope, attack, release, output_gain;
    int16_t tail[ECHO_DSP_FADE];
    size_t seen, head, pending;
    uint32_t faults;
    bool tuned, finished;
} echo_dsp;

/* Fresh state per utterance. Gain is a bounded final control, not auto gain. */
bool echo_dsp_init(echo_dsp *s, bool tuned, float output_gain);
/* RLCD listening-test profile: stronger low-cut and consonant presence. */
bool echo_dsp_init_rlcd(echo_dsp *s);
bool echo_dsp_init_rlcd_legacy(echo_dsp *s);
/* Output capacity must be >= count. Stateful across arbitrary chunk boundaries.
 * For tuned output, holds the last 8 ms for fade-out. Returns <= count.
 */
size_t echo_dsp_push(echo_dsp *s, const int16_t *input, size_t count, int16_t *output);
/* Output capacity >= ECHO_DSP_FADE. Emits pending tail, preserving sample count.
 * A second finish or push after finish emits nothing.
 */
size_t echo_dsp_finish(echo_dsp *s, int16_t *output);
#endif
