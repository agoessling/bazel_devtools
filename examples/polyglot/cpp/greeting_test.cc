#include "cpp/greeting.h"

#include <cassert>

auto main() -> int {
  assert(Greeting("Bazel") == "Hello, Bazel!");
  return 0;
}
