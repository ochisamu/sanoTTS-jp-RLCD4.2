#ifndef RLCD_PHONEMES_H
#define RLCD_PHONEMES_H
#include <stddef.h>
// Returns number of dropped invalid phonemes, or -1 on capacity/invalid input.
int phonemes_to_kana(const int *ids,int count,char *output,size_t capacity);
#endif
