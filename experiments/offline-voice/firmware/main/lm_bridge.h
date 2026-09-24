#pragma once
#include <stdbool.h>
#include <stddef.h>
bool lm_bridge_reply(const char *question, char *answer, size_t capacity, void (*send)(const char *));
