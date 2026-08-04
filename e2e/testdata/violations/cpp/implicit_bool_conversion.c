#include <stdbool.h>

static int Normalize(bool enabled) { return enabled ? 1 : 0; }

int main(void) { return Normalize(1) == 1 ? 0 : 1; }
