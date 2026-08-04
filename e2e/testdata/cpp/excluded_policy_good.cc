#include <span>

int Value();  // NOLINT(misc-use-internal-linkage)
int Scale(int value);  // NOLINT(misc-use-internal-linkage)
int First(std::span<const int> values);  // NOLINT(misc-use-internal-linkage)

int Value() { return 0; }

int Scale(int value) { return value + value * 2; }

int First(std::span<const int> values) { return values[0]; }
