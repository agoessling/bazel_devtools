#include "cpp/greeting.h"

#include <string>

auto Greeting(const std::string &name) -> std::string {
  const char *punctuation = 0;
  return "Hello, " + name + (punctuation == 0 ? "!" : "?");
}
