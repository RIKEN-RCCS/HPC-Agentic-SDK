/*
 * wss_probe_fp_events — discover which raw PMU event codes count
 *                       userspace floating-point operations.
 *
 * Usage:
 *   wss_probe_fp_events [0xNN ...]
 *
 * With no arguments, probes a default set of known FP event codes for
 * this architecture (aarch64: 0x74 FP_FIXED_OPS_SPEC, 0x75 FP_SCALE_OPS_SPEC).
 * Pass explicit codes to probe others — consult 'perf list' and your CPU's
 * PMU reference manual for candidates.
 *
 * All tests use exclude_kernel=1 (userspace only), matching exactly what
 * the profiler measures. perf stat without this flag picks up kernel FP ops
 * and gives misleading results.
 *
 * Output:
 *   Diagnostic lines on stderr.
 *   On stdout: "export WSS_PERF_FP_EVENTS=<comma-separated working codes>"
 *   Exit 0 if at least one event works, 1 if none.
 *
 * Typical usage:
 *   eval $(wss_probe_fp_events 2>/dev/null)
 *   echo $WSS_PERF_FP_EVENTS
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>
#include <errno.h>

static long _probe_perf_open(unsigned long config)
{
    struct perf_event_attr pe = {0};
    pe.size           = sizeof(pe);
    pe.type           = PERF_TYPE_RAW;
    pe.config         = config;
    pe.disabled       = 1;
    pe.exclude_kernel = 1;
    pe.exclude_hv     = 1;
    pe.inherit        = 0;
    return syscall(__NR_perf_event_open, &pe, 0, -1, -1, 0);
}

/*
 * FP microbenchmark.
 *
 * Keep several arrays live and reduce across all of them at the end so the
 * compiler cannot collapse the work down to a tiny scalar loop. The goal is
 * not to benchmark throughput; it is simply to generate an unambiguous stream
 * of userspace FP instructions for PMU validation.
 */
static double run_fp_work(void)
{
    enum { N = 256, REPS = 4000 };
    double a[N], b[N], c[N];

    for (int i = 0; i < N; i++) {
        a[i] = (double)(i + 1);
        b[i] = (double)(2 * i + 1) * 1e-3;
        c[i] = (double)(3 * i + 1) * 1e-6;
    }

    for (int rep = 0; rep < REPS; rep++) {
        for (int i = 0; i < N; i++) {
            double ai = a[i];
            double bi = b[i];
            double ci = c[i];

            ai = ai * 1.0000001 + bi * 0.9999999 + 1e-15;
            bi = bi * 1.0000002 + ci * 0.9999998 + 1e-16;
            ci = ci + ai * bi * 1e-12;

            a[i] = ai;
            b[i] = bi;
            c[i] = ci;
        }
    }

    double sum = 0.0;
    for (int i = 0; i < N; i++)
        sum += a[i] + b[i] + c[i];

    volatile double sink = sum;
    return (double)sink;
}

static long long probe_one(unsigned long code)
{
    long fd = _probe_perf_open(code);
    if (fd < 0) return -1;

    ioctl(fd, PERF_EVENT_IOC_RESET,   0);
    ioctl(fd, PERF_EVENT_IOC_ENABLE,  0);
    volatile double r = run_fp_work();
    (void)r;
    ioctl(fd, PERF_EVENT_IOC_DISABLE, 0);

    long long count = 0;
    read(fd, &count, sizeof(long long));
    close(fd);
    return count;
}

int main(int argc, char **argv)
{
    /* Architecture-specific default codes when none are supplied */
#ifdef __aarch64__
    unsigned long default_codes[] = {0x74, 0x75};
    const char   *default_names[] = {"FP_FIXED_OPS_SPEC (scalar/NEON/ASIMD)",
                                     "FP_SCALE_OPS_SPEC (SVE)"};
    int n_default = 2;
#else
    unsigned long *default_codes = NULL;
    const char   **default_names = NULL;
    int n_default = 0;
#endif

    unsigned long *codes;
    const char   **names;
    int n_codes;
    int free_codes = 0;

    if (argc > 1) {
        n_codes    = argc - 1;
        codes      = malloc(n_codes * sizeof(unsigned long));
        names      = malloc(n_codes * sizeof(const char *));
        free_codes = 1;
        for (int i = 0; i < n_codes; i++) {
            codes[i] = strtoul(argv[i + 1], NULL, 0);
            names[i] = "(user-supplied)";
        }
    } else if (n_default > 0) {
        codes  = default_codes;
        names  = default_names;
        n_codes = n_default;
    } else {
        fprintf(stderr,
                "No default event codes for this architecture.\n"
                "Consult 'perf list' and your CPU PMU manual, then pass\n"
                "codes explicitly: wss_probe_fp_events 0xNN 0xMM ...\n");
        return 1;
    }

    fprintf(stderr,
            "Probing PMU raw event codes for userspace FP ops"
            " (exclude_kernel=1):\n\n");

    /* Warm up: page faults, branch prediction */
    volatile double warmup = run_fp_work();
    (void)warmup;

    char working[256] = {0};
    int  n_working    = 0;

    for (int i = 0; i < n_codes; i++) {
        long long count = probe_one(codes[i]);
        if (count < 0) {
            fprintf(stderr, "  0x%02lx  %-40s  perf_event_open failed (%s)\n",
                    codes[i], names[i], strerror(errno));
        } else if (count == 0) {
            fprintf(stderr, "  0x%02lx  %-40s  0 ops"
                            " (not counting — wrong code or PMU not exposed)\n",
                    codes[i], names[i]);
        } else {
            fprintf(stderr, "  0x%02lx  %-40s  %lld ops  ✓\n",
                    codes[i], names[i], count);
            if (n_working > 0) strcat(working, ",");
            char buf[32];
            snprintf(buf, sizeof(buf), "0x%02lx", codes[i]);
            strcat(working, buf);
            n_working++;
        }
    }

    fprintf(stderr, "\n");

    if (n_working == 0) {
        fprintf(stderr,
                "No working FP event codes found.\n"
                "If PAPI works ('papi_avail' shows FP events), no action needed.\n"
                "Otherwise consult 'perf list' for raw event names and your\n"
                "CPU PMU manual for hex codes, then re-run with those codes.\n");
        if (free_codes) { free(codes); free((void *)names); }
        return 1;
    }

    /* Emit the export line to stdout for easy capture */
    printf("export WSS_PERF_FP_EVENTS=%s\n", working);

    if (free_codes) { free(codes); free((void *)names); }
    return 0;
}
