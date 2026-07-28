/*
 * wss_runtime_probe — authoritative runtime capability probe for WSS.
 *
 * This program exercises the same WSS instrumentation path used by real
 * profiled applications. It reports what the runtime actually managed to
 * measure, along with the FP event environment variable that was used.
 *
 * Output is machine-readable KEY=VALUE lines on stdout. WSS diagnostics stay
 * on stderr.
 *
 * Usage:
 *   wss_runtime_probe
 *   wss_runtime_probe 0x74,0x75
 *
 * With no argument, aarch64 defaults to WSS_PERF_FP_EVENTS=0x74,0x75 unless
 * the environment already sets WSS_PERF_FP_EVENTS. On other architectures the
 * environment is left untouched.
 */

#include <errno.h>
#include <mpi.h>
#include <papi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "wss_profiler.h"

#define PROBE_N     (256 * 1024)
#define PROBE_ITERS 2000

static void probe_kernel(double *x, long n, int iters)
{
    for (long i = 0; i < n; i++) {
        double v = x[i];
        for (int k = 0; k < iters; k++)
            v = v * 1.0000001 + 1e-10;
        x[i] = v;
    }
}

static void emit_result(const char *key, const char *value)
{
    printf("%s=%s\n", key, value ? value : "");
}

int main(int argc, char **argv)
{
    const char *requested_fp_events = NULL;
    const char *fp_events_provenance = "none";

    if (argc > 2) {
        fprintf(stderr, "usage: %s [fp_events]\n", argv[0]);
        return 2;
    }

    if (argc == 2) {
        requested_fp_events = argv[1];
        fp_events_provenance = "user_argument";
    }

#ifdef __aarch64__
    if ((!requested_fp_events || requested_fp_events[0] == '\0')
        && getenv("WSS_PERF_FP_EVENTS") == NULL) {
        requested_fp_events = "0x74,0x75";
        fp_events_provenance = "hardcoded_aarch64_default";
    }
#endif

    if ((!requested_fp_events || requested_fp_events[0] == '\0')
        && getenv("WSS_PERF_FP_EVENTS") != NULL) {
        fp_events_provenance = "inherited_environment";
    }

    if (requested_fp_events && requested_fp_events[0] != '\0') {
        if (setenv("WSS_PERF_FP_EVENTS", requested_fp_events, 1) != 0) {
            fprintf(stderr, "setenv(WSS_PERF_FP_EVENTS) failed: %s\n", strerror(errno));
            return 2;
        }
    }

    MPI_Init(&argc, &argv);
    WSS_INIT();

    double hot_mb = 0.0;
    double accessed_mb = 0.0;
    double access_events_m = 0.0;
    double gflop = 0.0;
    const char *fp_source = "none";
    const char *mem_source = "none";
    int rank = -1;

    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    if (rank == 0) {
        double *x = malloc(PROBE_N * sizeof(double));
        if (!x) {
            fprintf(stderr, "wss_runtime_probe: malloc failed\n");
            MPI_Abort(MPI_COMM_WORLD, 2);
        }

        for (long i = 0; i < PROBE_N; i++)
            x[i] = (double)(i + 1);

        WSS_BEGIN();
        probe_kernel(x, PROBE_N, PROBE_ITERS);

        _wss_active = 0;
        long long vals[8] = {0};
        if (_wss_eventset != PAPI_NULL)
            PAPI_stop(_wss_eventset, vals);
        long long perf_fp = _wss_perf_stop();
        long long ref_kb = _wss_read_referenced_kb();

        long long flops = perf_fp;
        for (int i = 0; i < _wss_nfp_events; i++)
            flops += vals[i];

        long long memops = 0;
        for (int i = _wss_nfp_events; i < _wss_nfp_events + _wss_nmem_events; i++)
            memops += vals[i];

        hot_mb = (ref_kb >= 0) ? ref_kb / 1024.0 : 0.0;
        accessed_mb = (memops * 8.0) / (1024.0 * 1024.0);
        access_events_m = memops / 1.0e6;
        gflop = flops / 1.0e9;

        if (_wss_nfp_events > 0)
            fp_source = "papi";
        else if (_wss_n_fp_fds > 0)
            fp_source = "perf_fallback";

        if (_wss_nmem_events > 0)
            mem_source = "papi";
        else if (_wss_n_mem_fds > 0)
            mem_source = "perf_mem_access";

        free(x);
    }

    MPI_Barrier(MPI_COMM_WORLD);

    if (rank == 0) {
        char buf[128];
        emit_result("ARCH",
#ifdef __aarch64__
                    "aarch64"
#elif defined(__x86_64__)
                    "x86_64"
#else
                    "unknown"
#endif
        );
        emit_result("CAPABILITY_TRUTH_SOURCE", "wss_runtime_probe");
        emit_result("WSS_PERF_FP_EVENTS_ENV", getenv("WSS_PERF_FP_EVENTS"));
        emit_result("FP_EVENTS_PROVENANCE", fp_events_provenance);

        snprintf(buf, sizeof(buf), "%d", _wss_nfp_events);
        emit_result("PAPI_FP_EVENT_COUNT", buf);

        snprintf(buf, sizeof(buf), "%d", _wss_nmem_events);
        emit_result("PAPI_MEM_EVENT_COUNT", buf);

        snprintf(buf, sizeof(buf), "%d", _wss_n_fp_fds);
        emit_result("PERF_FP_FD_COUNT", buf);

        snprintf(buf, sizeof(buf), "%d", _wss_n_mem_fds);
        emit_result("PERF_MEM_FD_COUNT", buf);

        emit_result("FP_SOURCE", fp_source);
        emit_result("MEM_SOURCE", mem_source);

        snprintf(buf, sizeof(buf), "%.6f", hot_mb);
        emit_result("HOT_MB", buf);

        snprintf(buf, sizeof(buf), "%.6f", accessed_mb);
        emit_result("ACCESSED_MB", buf);

        snprintf(buf, sizeof(buf), "%.6f", access_events_m);
        emit_result("ACCESS_EVENTS_M", buf);

        snprintf(buf, sizeof(buf), "%.6f", gflop);
        emit_result("GFLOP", buf);

        emit_result("HOT_BYTES_OK", hot_mb > 0.0 ? "1" : "0");
        emit_result("FP_OK", gflop > 0.0 ? "1" : "0");
        emit_result("MEM_BYTES_OK", accessed_mb > 0.0 ? "1" : "0");
        emit_result("MEM_OK", (accessed_mb > 0.0 || access_events_m > 0.0) ? "1" : "0");
    }

    MPI_Finalize();
    return 0;
}
