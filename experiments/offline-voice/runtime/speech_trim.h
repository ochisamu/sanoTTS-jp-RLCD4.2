#ifndef SPEECH_TRIM_H
#define SPEECH_TRIM_H
// Mono float PCM at 16 kHz, max 18 seconds. Conservative boundary trimming only.
// Returns 1 for a detected speech region, 0 to preserve the entire input.
int speech_trim(const float *audio,int count,int *begin,int *end);
#endif
