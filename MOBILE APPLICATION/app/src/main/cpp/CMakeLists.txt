cmake_minimum_required(VERSION 3.22.1)
project(maya_llama)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# llama.cpp options (keep build lean)
set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(LLAMA_CURL OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)

add_subdirectory(llama.cpp)

# JNI bridge
add_library(maya_llama SHARED native-lib.cpp)
target_include_directories(maya_llama PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/llama.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/llama.cpp/include
    ${CMAKE_CURRENT_SOURCE_DIR}/llama.cpp/ggml/include
)
find_library(log-lib log)
find_library(android-lib android)
target_link_libraries(maya_llama PRIVATE llama ggml ${log-lib} ${android-lib} ${CMAKE_THREAD_LIBS_INIT})
