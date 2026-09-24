#ifndef RLCD_CTC_RUNTIME_H
#define RLCD_CTC_RUNTIME_H
#include <stddef.h>
#include <stdint.h>
// Returns 0 on success. Output is time-major float logits; caller must ctc_free.
// qa: 0=float activations, 1=W8A8 projections, 2=+int8 QK, 3=+int8 PV,
// 4=+interpolated math/float local norms, 5=+reciprocal and fast rounding.
// Non-reentrant: qa>=4 lazily initializes shared lookup tables; use one worker.
int ctc_run(const void *blob,size_t blob_size,const float *audio,int samples,
            int quantize_activations,float **logits,int *frames,int *vocab);
void ctc_free(void *ptr);
int ctc_kernel_selftest(void);
void ctc_progress(const char *stage);
#endif
