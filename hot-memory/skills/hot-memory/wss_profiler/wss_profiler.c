/*
 * wss_profiler.c — Global variable definitions for wss_profiler.h.
 *
 * Compiled once into libwss_profiler.a so that all translation units
 * that include wss_profiler.h share a single copy of the profiler state.
 * Without this, each .c/.cc file that includes the header gets its own
 * static copy, and WSS_INIT() in main never initialises the _wss_rank
 * seen by WSS_BEGIN() in other files.
 */

#ifdef PROFILE_WSS

#include <papi.h>

int _wss_rank        = -1;
int _wss_eventset    = PAPI_NULL;  /* relies on PAPI_NULL == -1 */
int _wss_nfp_events  = 0;
int _wss_nmem_events = 0;
int _wss_nevents     = 0;
int _wss_papi_ok     = 0;
int _wss_active      = 0;
int _wss_fp_fds[8]   = {-1,-1,-1,-1,-1,-1,-1,-1}; /* perf_event_open fds for FP fallback */
int _wss_n_fp_fds    = 0;
int _wss_mem_fds[8]  = {-1,-1,-1,-1,-1,-1,-1,-1}; /* perf_event_open fds for mem_access fallback */
int _wss_n_mem_fds   = 0;

#endif
