#ifndef KLM_H
#define KLM_H
#include <stddef.h>
#include <stdint.h>
typedef struct klm klm;
/* Blob must remain alive and 16-byte aligned until close. Fixed v1 format. */
klm *klm_open(const void *blob, size_t bytes);
void klm_close(klm *m);
void klm_reset(klm *m);
int klm_encode(const klm *m, const char *text, int *ids, int capacity);
int klm_step(klm *m, int token, float *logits); /* next token or negative error */
int klm_append(const klm *m, int token, char *out, size_t capacity);
/* Orthographic kana punctuation -> sanoTTS pause marks, not full Japanese G2P. */
int klm_tts_text(const char *text, char *out, size_t capacity);
size_t klm_workspace_bytes(void);
int klm_kernel_selftest(void);
#endif
