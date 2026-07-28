/*
 * wss_profiler_f.c — Fortran-callable wrappers for wss_profiler.h.
 *
 * Usage from Fortran:
 *   call wss_init()
 *   call wss_begin()
 *   call some_kernel(...)
 *   call wss_end("kernel_name"//C_NULL_CHAR)
 *
 * Or with the provided Fortran module (wss_profiler_mod.f90):
 *   use wss_profiler_mod
 *   call wss_init()
 *   call wss_begin()
 *   call some_kernel(...)
 *   call wss_end_named("kernel_name")
 *
 * Build: compile this file with -DPROFILE_WSS -lpapi alongside your
 *        Fortran code. Without -DPROFILE_WSS the functions are empty stubs.
 */

#include "wss_profiler.h"

#ifdef PROFILE_WSS

void wss_init_(void)  { WSS_INIT(); }
void wss_begin_(void) { WSS_BEGIN(); }

void wss_end_(const char *name, int name_len)
{
    /* Fortran passes string length as a hidden argument. */
    /* Copy to a null-terminated C string. */
    char buf[256];
    if (name_len > 255) name_len = 255;
    memcpy(buf, name, name_len);
    buf[name_len] = '\0';
    /* Strip trailing spaces (Fortran pads strings). */
    while (name_len > 0 && buf[name_len - 1] == ' ') {
        buf[--name_len] = '\0';
    }
    WSS_END(buf);
}

#else

void wss_init_(void)  {}
void wss_begin_(void) {}
void wss_end_(const char *name, int name_len) { (void)name; (void)name_len; }

#endif
