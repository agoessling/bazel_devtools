#ifndef EXTERNAL_CPP_FIXTURE_VENDOR_POLICY_H_
#define EXTERNAL_CPP_FIXTURE_VENDOR_POLICY_H_

static inline int vendor_read(void) {
  return *((volatile int *)0x40000000ul);
}

#endif  // EXTERNAL_CPP_FIXTURE_VENDOR_POLICY_H_
