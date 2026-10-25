# PYATL_FETCH_DEPS: algotradelib's main branch from GitHub, configured with its own ATL_FETCH_DEPS=ON, so
# Boost and Eigen are fetched too (see the library's cmake/deps.cmake). OpenSSL comes from the system.
#
# main, not a pinned commit: the library is experimental, and a change to it that breaks pyatl should show
# up at once. Pin a release tag once the library has one.
#
# A local checkout instead, for a test only (never committed):
#   -DFETCHCONTENT_SOURCE_DIR_ALGOTRADELIB=/path/to/algotradelib
if(CMAKE_VERSION VERSION_LESS 3.24)
    message(FATAL_ERROR "PYATL_FETCH_DEPS needs CMake 3.24 or newer (the library's ATL_FETCH_DEPS does).")
endif()
include(FetchContent)

set(ATL_FETCH_DEPS ON CACHE BOOL "Fetch algotradelib's dependencies" FORCE)
FetchContent_Declare(algotradelib
    GIT_REPOSITORY https://github.com/algotradelib/algotradelib.git
    GIT_TAG main
    GIT_SHALLOW TRUE
    EXCLUDE_FROM_ALL
)
FetchContent_MakeAvailable(algotradelib)
