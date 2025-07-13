# **Changelog**

## v0.3.0 -- 2025-01-15

    In init_prod() and init_debug() remove the outputs/include directory.

## v0.3.1 -- 2025-01-19
rebuild test directory in init-debug or init-prod, not in each test command

## v0.3.2 -- 2025-04-14
break compile if some fails

## v0.3.3 -- 2025-04-24
rebuild test directory in each test command

## v0.3.5 -- 2025-06-08
add test_verbose

## v0.3.6 -- 2025-06-16
read .config to get what compiler to use (CLANG, GCC, MUSL)

## v0.3.7 -- 2025-06-16
Fix if directory to remove not exist

## v0.3.8 -- 2025-06-22
generate static libraries
Now you can generate static or dynamic version of Yunetas libraries and tools.
Installing in `outputs_static` or `outputs` directory.
And new commands `init-prod-static` and `init-debug-static`
The static version are built with:
    cmake -DCMAKE_TOOLCHAIN_FILE={base_path}/tools/cmake/musl-toolchain.cmake

## v0.4.0 -- 23-Jun-2025
In tests do "make install"

## v0.4.1 -- 23-Jun-2025
Simplify tests commands

## v0.4.2 -- 23-Jun-2025
Simplify init commands, get configuration from .config (menuconfig)

## v0.4.3 -- 24-Jun-2025
Use /usr/bin/musl-gcc instead of /usr/local/bin/musl-gcc

## v0.4.4 -- 25-Jun-2025
Add directory "kernel/c/libjwt"

## v0.5.0 -- 27-Jun-2025
Fix compiler type

## v0.5.1 -- 13-Jul-2025
In test do make install, make clean, make install
