# SPDX-License-Identifier: GPL-2.0-or-later
# The headless host uses source-built dependencies, not Blender's old VC12 bundle.
if(NOT MSVC)
  message(FATAL_ERROR "The Windows host build requires MSVC")
endif()
macro(find_package_wrapper)
  find_package(${ARGV})
endmacro()
list(PREPEND CMAKE_PREFIX_PATH "${INTERNAL_DEPS_ROOT}")
find_package(ZLIB REQUIRED)
find_package(PNG REQUIRED)
find_package(JPEG REQUIRED)
find_package(Freetype REQUIRED)
set(FREETYPE_LIBRARY ${FREETYPE_LIBRARIES})
set(PTHREADS_INCLUDE_DIRS "${INTERNAL_DEPS_ROOT}/include")
set(PTHREADS_LIBRARIES "${INTERNAL_DEPS_ROOT}/lib/pthreadVC3.lib")
blender_include_dirs_sys("${PTHREADS_INCLUDE_DIRS}")
add_definitions(-DWIN32 -D_CONSOLE -D_LIB -D_WIN32_WINNT=0x0601
  -D_CRT_NONSTDC_NO_DEPRECATE -D_CRT_SECURE_NO_DEPRECATE
  -D_SCL_SECURE_NO_DEPRECATE -D_ALLOW_KEYWORD_MACROS)
# Recent MSVC warns (C5287) when legacy CustomData flags combine enum types.
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} /J /Gd /wd5287")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /J /Gd /EHsc /wd5287")
list(APPEND PLATFORM_LINKLIBS ws2_32 vfw32 winmm kernel32 user32 gdi32
  comdlg32 advapi32 shfolder shell32 ole32 oleaut32 uuid psapi Dbghelp)
