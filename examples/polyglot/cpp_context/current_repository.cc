#include "cpp_context/current_repository.h"

#include <string_view>

auto CurrentRepository() -> std::string_view { return BAZEL_CURRENT_REPOSITORY; }
