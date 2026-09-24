#pragma once
#include <stddef.h>
/* Whole-phrase local lookup, never a neural generation claim. Flash pointers. */
typedef struct { const char *id,*reading,*display; } reply_fact;
int reply_knowledge_lookup(const char *question,reply_fact *out);
/* Exact known reading -> display form. Unknown/ambiguous readings remain kana. */
const char *reply_display_text(const char *reading);
