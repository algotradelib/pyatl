cmake_minimum_required(VERSION 3.18)
project(pyatl LANGUAGES CXX)

option(PYATL_FETCH_DEPS "Fetch algotradelib and its dependencies with FetchContent instead of finding an installed one (CI)" OFF)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# The extension is a shared library; anything compiled into it (a fetched Boost.JSON) must be position independent.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module ${SKBUILD_SABI_COMPONENT})
find_package(nanobind CONFIG REQUIRED)

if(PYATL_FETCH_DEPS)
    include(cmake/deps.cmake)
else()
    # An installed algotradelib: CMAKE_PREFIX_PATH or algotradelib_DIR points at it.
    find_package(algotradelib CONFIG REQUIRED)
endif()

# STABLE_ABI: one wheel for every Python from 3.12. LTO: what made the binding comparison fair in the lab
# (pybind11 turns it on by itself; nanobind does not).
nanobind_add_module(_core STABLE_ABI NB_STATIC LTO
    src/bindings/module.cpp
    src/bindings/types.cpp
    src/bindings/series.cpp
    src/bindings/backtest.cpp
)
# The extension's own headers: compiled into it, never installed.
target_include_directories(_core PRIVATE include)
target_link_libraries(_core PRIVATE algotradelib::algotradelib)
install(TARGETS _core LIBRARY DESTINATION pyatl)

# Type stubs for _core, so editors know Bar and Context.
nanobind_add_stub(_core_stub
    MODULE _core
    OUTPUT _core.pyi
    PYTHON_PATH $<TARGET_FILE_DIR:_core>
    DEPENDS _core
)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/_core.pyi DESTINATION pyatl)
