/* SPDX-License-Identifier: MIT */
#include "echo_dsp.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    echo_dsp s;
    if (argc == 2 && !strcmp(argv[1], "--selftest")) {
        assert(!echo_dsp_init(&s, true, NAN));
        assert(!echo_dsp_init(&s, true, 2));
        assert(echo_dsp_init(&s, true, 1));
        int16_t x[200] = {1}, y[200];
        s.filters[0].z1 = NAN;
        echo_dsp_push(&s, x, 200, y);
        assert(s.faults == 1);
        echo_dsp_finish(&s, y);
        assert(echo_dsp_finish(&s, y) == 0);
        assert(echo_dsp_push(&s, x, 1, y) == 0);
        assert(echo_dsp_init(&s, true, 1));
        assert(s.faults == 0 && s.seen == 0 && s.pending == 0);
        return 0;
    }
    if (argc != 4) return 2;
    int chunk = atoi(argv[1]);
    if (chunk < 1 || chunk > 512 || !echo_dsp_init(&s, atoi(argv[2]) != 0, strtof(argv[3], NULL))) return 2;
    if(atoi(argv[2])==2 && !echo_dsp_init_rlcd(&s)) return 2;
    if(atoi(argv[2])==3 && !echo_dsp_init_rlcd_legacy(&s)) return 2;
    int16_t in[512], out[512]; size_t n;
    while ((n = fread(in, sizeof(int16_t), chunk, stdin)) != 0) {
        size_t count = echo_dsp_push(&s, in, n, out);
        if (fwrite(out, sizeof(int16_t), count, stdout) != count) return 3;
    }
    n = echo_dsp_finish(&s, out);
    if (fwrite(out, sizeof(int16_t), n, stdout) != n || s.faults) return 4;
    return 0;
}
