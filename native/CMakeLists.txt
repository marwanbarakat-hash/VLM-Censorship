cmake_minimum_required(VERSION 3.20)
project(ScreenCensorEngine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Safety Sanitizers: AddressSanitizer and UndefinedBehaviorSanitizer
# Intercepts all memory safety violations, out-of-bounds access, and leaks at runtime
add_compile_options(
    -fsanitize=address,undefined
    -fno-omit-frame-pointer
    -Wall
    -Wextra
    -Wpedantic
    -Wconversion
    -O2
)

add_link_options(-fsanitize=address,undefined)

# Dependencies: OpenCV (Installed via Homebrew: brew install opencv)
find_package(OpenCV REQUIRED)

include_directories(${OpenCV_INCLUDE_DIRS})

add_executable(censor_engine src/main.cpp)

target_link_libraries(censor_engine PRIVATE ${OpenCV_LIBS})