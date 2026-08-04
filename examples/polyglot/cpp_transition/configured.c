#include "vendor_policy.h"

static int Normalize(int value) {
  if (value != 0) {
    return 1;
  }
  return 0;
}

int main(void) { return Normalize(vendor_read()) == 1 ? 0 : 1; }
