#include "cpp/greeting.h"

#include <string>

auto Greeting( const std::string& name )->std::string{return "Hello, " + name + "!";}
