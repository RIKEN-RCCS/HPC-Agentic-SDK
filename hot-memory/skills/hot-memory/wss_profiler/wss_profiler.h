/*
 * wss_profiler.h — Per-kernel working set size (WSS), FLOP, and memory
 *                  traffic profiler.
 *
 * Usage:
 *   1. #include "wss_profiler.h" in any file where you call WSS_* macros.
 *   2. Call WSS_INIT() once after MPI_Init().
 *   3. Wrap each kernel call with WSS_BEGIN() / WSS_END("kernel_name").
 *   4. Build with: -DPROFILE_WSS -lwss_profiler -lpapi
 *      (Without -DPROFILE_WSS, all macros compile away to nothing.)
 *      The header uses extern declarations; the definitions are in
 *      wss_profiler.c, compiled into libwss_profiler.a.
 *
 * Output (to stderr, rank 0 only):
 *   [WSS] kernel_name     512.0 MB hot   1024.0 MB accessed   0.480 GFLOP   0.98 FLOP/byte-hot   0.47 FLOP/byte-accessed
 *
 *   "MB accessed" and "FLOP/byte-accessed" are only reported when PAPI
 *   load/store counters are available. On aarch64 systems where those PAPI
 *   events are missing, the profiler falls back to raw PMU mem_access events
 *   and reports "M accesses" plus "FLOP/access" instead.
 *
 * FP counting:
 *   PAPI is tried first. If PAPI provides no FP events (e.g. libpfm4 doesn't
 *   know the CPU), the profiler falls back to perf_event_open with raw PMU
 *   event codes supplied at runtime via the WSS_PERF_FP_EVENTS env var.
 *
 *   WSS_PERF_FP_EVENTS is a comma-separated list of hex event codes to open,
 *   one fd per code. Their counts are summed. Use wss_probe_fp_events to
 *   discover which codes work on this machine before running the profiler:
 *
 *     eval $(wss_probe_fp_events)         # sets WSS_PERF_FP_EVENTS
 *     mpirun -np 4 ./solver ...           # profiler reads the env var
 *
 *   On ARM Grace, both 0x74 (scalar/NEON/ASIMD) and 0x75 (SVE) are needed
 *   for complete FP coverage. The probe tool discovers the right codes.
 *   If WSS_PERF_FP_EVENTS is not set and PAPI has no FP events, FLOPs = 0.
 *
 * Requirements:
 *   - Linux amd64 or aarch64 (uses /proc/self/clear_refs and /proc/self/smaps)
 *   - PAPI (libpapi-dev) for FP and load/store counting (optional: degrades
 *     gracefully; perf_event_open fallback used when PAPI FP unavailable, and
 *     mem_access fallback used when PAPI load/store unavailable on aarch64)
 *   - MPI (for rank filtering)
 *   - OpenMP should be disabled or ignored for analysis; counters only
 *     measure the main thread
 *   - Root or CAP_SYS_RESOURCE to write clear_refs
 */

#pragma once
#ifndef WSS_PROFILER_H
#define WSS_PROFILER_H

#ifdef PROFILE_WSS

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>
#include <mpi.h>
#include <papi.h>

/* ── internal state ─────────────────────────────────────────────────────── */
/*
 * Declared extern so all translation units share one copy.
 * The definitions live in wss_profiler.c, compiled into libwss_profiler.a.
 * Link with: -lwss_profiler -lpapi
 */
#define WSS_MAX_FP_EVENTS 8       /* max raw PMU event codes in WSS_PERF_FP_EVENTS */

extern int    _wss_rank;
extern int    _wss_eventset;
extern int    _wss_nfp_events;              /* how many PAPI FP counters are live */
extern int    _wss_nmem_events;             /* how many PAPI load/store counters are live */
extern int    _wss_nevents;                 /* total PAPI counters: FP + mem */
extern int    _wss_papi_ok;                 /* PAPI library initialized */
extern int    _wss_active;                  /* 1 between WSS_BEGIN and WSS_END */
extern int    _wss_fp_fds[WSS_MAX_FP_EVENTS]; /* perf_event_open fds for FP fallback */
extern int    _wss_n_fp_fds;               /* number of open perf FP fds */
extern int    _wss_mem_fds[WSS_MAX_FP_EVENTS]; /* perf_event_open fds for mem_access fallback */
extern int    _wss_n_mem_fds;              /* number of open perf mem fds */

/* ── internal helpers (defined inline to avoid duplicate-symbol errors) ─── */

static inline void _wss_papi_init(void)
{
    int ret = PAPI_library_init(PAPI_VER_CURRENT);
    if (ret != PAPI_VER_CURRENT) {
        fprintf(stderr, "[WSS] PAPI library init failed: %s\n",
                PAPI_strerror(ret));
        return;
    }
    _wss_papi_ok = 1;

    if (PAPI_create_eventset(&_wss_eventset) != PAPI_OK) {
        fprintf(stderr, "[WSS] PAPI_create_eventset failed\n");
        return;
    }

    /* ── FP counters ── */
    /* Prefer separate DP/SP counters; fall back to combined FP counter. */
    int has_dp = (PAPI_add_event(_wss_eventset, PAPI_DP_OPS) == PAPI_OK);
    int has_sp = (PAPI_add_event(_wss_eventset, PAPI_SP_OPS) == PAPI_OK);

    if (!has_dp && !has_sp) {
        if (PAPI_add_event(_wss_eventset, PAPI_FP_OPS) == PAPI_OK) {
            _wss_nfp_events = 1;
            fprintf(stderr,
                    "[WSS] Using PAPI_FP_OPS (DP_OPS/SP_OPS unavailable)\n");
        } else {
            fprintf(stderr,
                    "[WSS] PAPI: no FP events available\n");
        }
    } else {
        _wss_nfp_events = has_dp + has_sp;
    }

    /* ── Load/Store counters for total bytes accessed ── */
    int has_ld = (PAPI_add_event(_wss_eventset, PAPI_LD_INS) == PAPI_OK);
    int has_sr = (PAPI_add_event(_wss_eventset, PAPI_SR_INS) == PAPI_OK);
    _wss_nmem_events = has_ld + has_sr;

    if (_wss_nmem_events == 0) {
        fprintf(stderr,
                "[WSS] No load/store PAPI events — total bytes accessed will be 0\n");
    }

    _wss_nevents = _wss_nfp_events + _wss_nmem_events;

    if (_wss_nevents == 0) {
        PAPI_destroy_eventset(&_wss_eventset);
        _wss_eventset = PAPI_NULL;
    }
}

/*
 * _wss_perf_mem_init() — open perf_event_open fds for memory-access counting.
 *
 * Called after _wss_papi_init(). Only activates when PAPI provided no memory
 * events (_wss_nmem_events == 0). On aarch64, if WSS_PERF_MEM_EVENTS is not
 * set, default to 0x13 (architectural MEM_ACCESS).
 */
static inline void _wss_perf_mem_init(void)
{
    if (_wss_nmem_events > 0)
        return;  /* PAPI already has memory access covered */

    const char *env = getenv("WSS_PERF_MEM_EVENTS");
#ifdef __aarch64__
    if (!env || env[0] == '\0')
        env = "0x13";
#endif
    if (!env || env[0] == '\0') {
        fprintf(stderr, "[WSS] WSS_PERF_MEM_EVENTS not set — total memory"
                        " accesses via perf_event_open disabled.\n");
        return;
    }

    char buf[256];
    strncpy(buf, env, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';

    char *tok = buf;
    char *next;
    while (tok && *tok && _wss_n_mem_fds < WSS_MAX_FP_EVENTS) {
        next = strchr(tok, ',');
        if (next) *next++ = '\0';

        while (*tok == ' ' || *tok == '\t') tok++;

        unsigned long code = strtoul(tok, NULL, 0);
        if (code == 0) { tok = next; continue; }

        struct perf_event_attr pe = {0};
        pe.size           = sizeof(pe);
        pe.type           = PERF_TYPE_RAW;
        pe.config         = code;
        pe.disabled       = 1;
        pe.exclude_kernel = 1;
        pe.exclude_hv     = 1;
        pe.inherit        = 0;

        int fd = (int)syscall(__NR_perf_event_open, &pe,
                              0 /*pid: self*/, -1 /*cpu: any*/,
                              -1 /*group*/, 0 /*flags*/);
        if (fd < 0) {
            fprintf(stderr, "[WSS] perf_event_open(mem event=0x%lx) failed: %m"
                            " — skipping this code\n", code);
            tok = next;
            continue;
        }

        fprintf(stderr, "[WSS] perf_event_open memory fallback: event 0x%lx ✓\n",
                code);
        _wss_mem_fds[_wss_n_mem_fds++] = fd;
        tok = next;
    }

    if (_wss_n_mem_fds == 0)
        fprintf(stderr, "[WSS] No WSS_PERF_MEM_EVENTS codes worked —"
                        " total memory accesses will be 0\n");
    else
        fprintf(stderr, "[WSS] Using %d perf_event_open fd(s) for memory"
                        " access counting\n", _wss_n_mem_fds);
}

/*
 * _wss_perf_fp_init() — open perf_event_open fds for FP counting.
 *
 * Called after _wss_papi_init(). Only activates when PAPI provided no FP
 * events (_wss_nfp_events == 0).
 *
 * Reads WSS_PERF_FP_EVENTS from the environment — a comma-separated list of
 * raw PMU event codes in hex, e.g. "0x74,0x75". One fd is opened per code;
 * their counts are summed at WSS_END. An init-time smoke test is run for
 * diagnostics, but explicitly supplied codes are still kept even if that
 * smoke test reads zero. Some MPI launch modes produce false
 * negatives in the smoke loop even when the real profiled kernel counts.
 *
 * Obtain the right codes for your machine using the probe tool:
 *   eval $(wss_probe_fp_events)
 *   mpirun -np 4 ./solver ...
 *
 * If WSS_PERF_FP_EVENTS is not set, FP counting via this path is skipped
 * (PAPI may still provide it; otherwise FLOPs will be 0).
 */
static inline void _wss_perf_fp_init(void)
{
    if (_wss_nfp_events > 0)
        return;  /* PAPI already has FP covered */

    const char *env = getenv("WSS_PERF_FP_EVENTS");
    if (!env || env[0] == '\0') {
        fprintf(stderr, "[WSS] WSS_PERF_FP_EVENTS not set — FP counting via"
                        " perf_event_open disabled. Run eval $(wss_probe_fp_events)"
                        " before profiling to enable it.\n");
        return;
    }

    /* Parse comma-separated hex codes, e.g. "0x74,0x75" */
    char buf[256];
    strncpy(buf, env, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';

    char *tok = buf;
    char *next;
    while (tok && *tok && _wss_n_fp_fds < WSS_MAX_FP_EVENTS) {
        /* find next comma */
        next = strchr(tok, ',');
        if (next) *next++ = '\0';

        /* trim whitespace */
        while (*tok == ' ' || *tok == '\t') tok++;

        unsigned long code = strtoul(tok, NULL, 0);
        if (code == 0) { tok = next; continue; }

        struct perf_event_attr pe = {0};
        pe.size           = sizeof(pe);
        pe.type           = PERF_TYPE_RAW;
        pe.config         = code;
        pe.disabled       = 1;
        pe.exclude_kernel = 1;
        pe.exclude_hv     = 1;
        pe.inherit        = 0;

        int fd = (int)syscall(__NR_perf_event_open, &pe,
                              0 /*pid: self*/, -1 /*cpu: any*/,
                              -1 /*group*/, 0 /*flags*/);
        if (fd < 0) {
            fprintf(stderr, "[WSS] perf_event_open(event=0x%lx) failed: %m"
                            " — skipping this code\n", code);
            tok = next;
            continue;
        }

        /* Smoke-test: verify the counter increments for userspace FP.
         * Keep several arrays live and reduce across all of them so the
         * compiler cannot optimize the workload down to a tiny scalar case.
         * perf_event_open can succeed but read 0 forever when the PMU
         * is not accessible from userspace (some VMs or restricted environments). */
        ioctl(fd, PERF_EVENT_IOC_RESET,  0);
        ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);
        {
            enum { _WSS_SMOKE_N = 256, _WSS_SMOKE_REPS = 4000 };
            double _wss_a[_WSS_SMOKE_N], _wss_b[_WSS_SMOKE_N], _wss_c[_WSS_SMOKE_N];
            for (int _k = 0; _k < _WSS_SMOKE_N; _k++) {
                _wss_a[_k] = (double)(_k + 1);
                _wss_b[_k] = (double)(2 * _k + 1) * 1e-3;
                _wss_c[_k] = (double)(3 * _k + 1) * 1e-6;
            }
            for (int _rep = 0; _rep < _WSS_SMOKE_REPS; _rep++) {
                for (int _k = 0; _k < _WSS_SMOKE_N; _k++) {
                    double _wss_ai = _wss_a[_k];
                    double _wss_bi = _wss_b[_k];
                    double _wss_ci = _wss_c[_k];
                    _wss_ai = _wss_ai * 1.0000001 + _wss_bi * 0.9999999 + 1e-15;
                    _wss_bi = _wss_bi * 1.0000002 + _wss_ci * 0.9999998 + 1e-16;
                    _wss_ci = _wss_ci + _wss_ai * _wss_bi * 1e-12;
                    _wss_a[_k] = _wss_ai;
                    _wss_b[_k] = _wss_bi;
                    _wss_c[_k] = _wss_ci;
                }
            }
            double _wss_sum = 0.0;
            for (int _k = 0; _k < _WSS_SMOKE_N; _k++)
                _wss_sum += _wss_a[_k] + _wss_b[_k] + _wss_c[_k];
            volatile double _wss_sink = _wss_sum; (void)_wss_sink;
        }
        ioctl(fd, PERF_EVENT_IOC_DISABLE, 0);
        long long smoke_count = 0;
        ssize_t smoke_read = read(fd, &smoke_count, sizeof(long long));
        ioctl(fd, PERF_EVENT_IOC_RESET, 0);

        if (smoke_read != (ssize_t)sizeof(long long)) {
            fprintf(stderr, "[WSS] perf_event_open(event=0x%lx) smoke read failed: %m"
                            " — keeping this fd because WSS_PERF_FP_EVENTS was"
                            " explicitly set\n", code);
        } else if (smoke_count == 0) {
            fprintf(stderr, "[WSS] perf_event_open(event=0x%lx) opened but smoke=0"
                            " inside WSS_INIT — keeping this fd and letting the"
                            " real profiled kernel decide\n", code);
        } else {
            fprintf(stderr, "[WSS] perf_event_open FP fallback: event 0x%lx"
                            " smoke=%lld ops ✓\n", code, smoke_count);
        }

        _wss_fp_fds[_wss_n_fp_fds++] = fd;
        tok = next;
    }

    if (_wss_n_fp_fds == 0)
        fprintf(stderr, "[WSS] No WSS_PERF_FP_EVENTS codes worked — FLOPs will be 0\n");
    else
        fprintf(stderr, "[WSS] Using %d perf_event_open fd(s) for FP counting\n",
                _wss_n_fp_fds);
}

/* Reset and enable all perf FP fds — called at WSS_BEGIN */
static inline void _wss_perf_start(void)
{
    for (int _i = 0; _i < _wss_n_fp_fds; _i++) {
        ioctl(_wss_fp_fds[_i], PERF_EVENT_IOC_RESET,  0);
        ioctl(_wss_fp_fds[_i], PERF_EVENT_IOC_ENABLE, 0);
    }
}

/* Disable all perf FP fds and return sum of counts — called at WSS_END */
static inline long long _wss_perf_stop(void)
{
    long long _total = 0;
    for (int _i = 0; _i < _wss_n_fp_fds; _i++) {
        ioctl(_wss_fp_fds[_i], PERF_EVENT_IOC_DISABLE, 0);
        long long _c = 0;
        read(_wss_fp_fds[_i], &_c, sizeof(long long));
        _total += _c;
    }
    return _total;
}

/* Reset and enable all perf memory-access fds — called at WSS_BEGIN */
static inline void _wss_perf_mem_start(void)
{
    for (int _i = 0; _i < _wss_n_mem_fds; _i++) {
        ioctl(_wss_mem_fds[_i], PERF_EVENT_IOC_RESET,  0);
        ioctl(_wss_mem_fds[_i], PERF_EVENT_IOC_ENABLE, 0);
    }
}

/* Disable all perf memory-access fds and return sum of counts — called at WSS_END */
static inline long long _wss_perf_mem_stop(void)
{
    long long _total = 0;
    for (int _i = 0; _i < _wss_n_mem_fds; _i++) {
        ioctl(_wss_mem_fds[_i], PERF_EVENT_IOC_DISABLE, 0);
        long long _c = 0;
        read(_wss_mem_fds[_i], &_c, sizeof(long long));
        _total += _c;
    }
    return _total;
}

static inline void _wss_clear_refs(void)
{
    FILE *f = fopen("/proc/self/clear_refs", "w");
    if (!f) {
        fprintf(stderr, "[WSS] cannot open /proc/self/clear_refs: %m\n"
                        "[WSS] need root or CAP_SYS_RESOURCE\n");
        return;
    }
    fputs("1\n", f);
    fclose(f);
}

static inline long long _wss_read_referenced_kb(void)
{
    FILE *f = fopen("/proc/self/smaps", "r");
    if (!f) {
        fprintf(stderr, "[WSS] cannot open /proc/self/smaps: %m\n");
        return -1;
    }
    char line[256];
    long long total = 0;
    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "Referenced:", 11) == 0) {
            long long kb = 0;
            sscanf(line + 11, "%lld", &kb);
            total += kb;
        }
    }
    fclose(f);
    return total;
}

/* ── public macros ──────────────────────────────────────────────────────── */

/*
 * WSS_INIT() — call once after MPI_Init().
 * Identifies rank 0, initialises PAPI (and perf fallback if needed),
 * prints a startup message.
 */
#define WSS_INIT() \
    do { \
        MPI_Comm_rank(MPI_COMM_WORLD, &_wss_rank); \
        if (_wss_rank == 0) { \
            _wss_papi_init(); \
            _wss_perf_fp_init(); \
            _wss_perf_mem_init(); \
            fprintf(stderr, "[WSS] Profiling active on rank 0\n"); \
        } \
    } while (0)

/*
 * WSS_BEGIN() — place immediately before the kernel call.
 * Clears the Referenced bits and starts counters (PAPI and/or perf).
 */
#define WSS_BEGIN() \
    do { \
        if (_wss_rank == 0) { \
            if (_wss_active) { \
                fprintf(stderr, \
                        "[WSS] ERROR: WSS_BEGIN() called while already active" \
                        " — nesting is not supported. End the current" \
                        " measurement with WSS_END() before starting a" \
                        " new one.\n"); \
            } else { \
                _wss_active = 1; \
                _wss_clear_refs(); \
                if (_wss_eventset != PAPI_NULL) \
                    PAPI_start(_wss_eventset); \
                _wss_perf_start(); \
                _wss_perf_mem_start(); \
            } \
        } \
    } while (0)

/*
 * WSS_END(name) — place immediately after the kernel call.
 * Stops counters, reads /proc/self/smaps, prints the report line.
 *
 * name: string literal identifying this kernel in the output.
 *
 * Counter layout in _wss_vals[]:
 *   [0..nfp-1]  = FP counters (DP_OPS, SP_OPS, or FP_OPS)
 *   [nfp..nfp+nmem-1] = memory counters (LD_INS, SR_INS)
 */
#define WSS_END(name) \
    do { \
        if (_wss_rank == 0) { \
            if (!_wss_active) { \
                fprintf(stderr, \
                        "[WSS] ERROR: WSS_END(\"%s\") called without a" \
                        " matching WSS_BEGIN().\n", (name)); \
            } else { \
            _wss_active = 0; \
            long long _wss_vals[8] = {0}; \
            if (_wss_eventset != PAPI_NULL) \
                PAPI_stop(_wss_eventset, _wss_vals); \
            long long _wss_perf_fp = _wss_perf_stop(); \
            long long _wss_perf_mem = _wss_perf_mem_stop(); \
            long long _wss_ref_kb  = _wss_read_referenced_kb(); \
            long long _wss_flops   = _wss_perf_fp; \
            for (int _i = 0; _i < _wss_nfp_events; _i++) \
                _wss_flops += _wss_vals[_i]; \
            long long _wss_memops  = _wss_perf_mem; \
            for (int _i = _wss_nfp_events; \
                 _i < _wss_nfp_events + _wss_nmem_events; _i++) \
                _wss_memops += _wss_vals[_i]; \
            double _wss_hot_mb     = (_wss_ref_kb >= 0) \
                                     ? _wss_ref_kb / 1024.0 : 0.0; \
            double _wss_gflop      = _wss_flops / 1.0e9; \
            double _wss_accessed_mb = (_wss_memops * 8.0) / (1024.0 * 1024.0); \
            double _wss_maccess_m = _wss_memops / 1.0e6; \
            double _wss_fpb_hot    = (_wss_ref_kb > 0) \
                                     ? (double)_wss_flops \
                                       / ((double)_wss_ref_kb * 1024.0) \
                                     : 0.0; \
            double _wss_fpb_acc    = (_wss_accessed_mb > 0.0) \
                                     ? _wss_gflop * 1024.0 / _wss_accessed_mb \
                                     : 0.0; \
            double _wss_flop_per_access = (_wss_memops > 0) \
                                          ? (double)_wss_flops / (double)_wss_memops \
                                          : 0.0; \
            if (_wss_nmem_events > 0) { \
                fprintf(stderr, \
                        "[WSS] %-24s %8.1f MB hot  %8.1f MB accessed" \
                        "  %8.3f GFLOP  %6.2f FLOP/B-hot  %6.2f FLOP/B-acc\n", \
                        (name), _wss_hot_mb, _wss_accessed_mb, \
                        _wss_gflop, _wss_fpb_hot, _wss_fpb_acc); \
            } else if (_wss_n_mem_fds > 0) { \
                fprintf(stderr, \
                        "[WSS] %-24s %8.1f MB hot  %8.1f M accesses" \
                        "  %8.3f GFLOP  %6.2f FLOP/B-hot  %6.2f FLOP/access\n", \
                        (name), _wss_hot_mb, _wss_maccess_m, \
                        _wss_gflop, _wss_fpb_hot, _wss_flop_per_access); \
            } else { \
                fprintf(stderr, \
                        "[WSS] %-24s %8.1f MB hot  %8.1f MB accessed" \
                        "  %8.3f GFLOP  %6.2f FLOP/B-hot  %6.2f FLOP/B-acc\n", \
                        (name), _wss_hot_mb, _wss_accessed_mb, \
                        _wss_gflop, _wss_fpb_hot, _wss_fpb_acc); \
            } \
            } \
        } \
    } while (0)

#else /* ── PROFILE_WSS not defined: compile everything away ─────────────── */

#define WSS_INIT()      do {} while (0)
#define WSS_BEGIN()     do {} while (0)
#define WSS_END(name)   do {} while (0)

#endif /* PROFILE_WSS */
#endif /* WSS_PROFILER_H */
