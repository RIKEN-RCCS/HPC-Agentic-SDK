---
name: rccs-cloud-demo
description: Interactive demo of the R-CCS Cloud plugin — walks through facility info, live cluster status, docs search, filesystem access, and job submission on the RIKEN R-CCS Cloud. User-invocable with /rccs-cloud-demo.
user-invocable: true
---

# R-CCS Cloud plugin demo

Run each step in order. Present results as a readable narrative — not raw JSON
dumps. Use markdown headers and tables. Pause after each step and show output
before moving on.

---

## Step 1 — Facility overview

Call `get_facility`. Present the key facts:
- One sentence leading with what the R-CCS Cloud is: a heterogeneous research
  testbed with many partition families.
- A table grouping partitions by hardware family (CPU-only | NVIDIA GPU | AMD GPU
  | Intel GPU) with columns: partition, node count, key hardware, module command.
- Note the special cases: ai-h100l-pu (30 min max), qc-h100 (under repair),
  qc-mi210 (GPU in progress), ng-dgx (Ubuntu).

---

## Step 2 — Live cluster status

Call `get_resources`. For each partition show a mini utilization bar:

```
genoa     ██████████  0/14 idle
qc-gh200  ███░░░░░░░  4/6 idle
```

(Use █ for allocated, ░ for idle, scaled to ~10 chars; add the idle count in
plain text.) Point out which partitions have idle capacity right now — those are
where a job would start fastest.

---

## Step 3 — Documentation search

Call `search_docs` with *"what makes the A64FX partition different from x86
nodes, and what should I know before running code there?"*

This surfaces something genuinely R-CCS Cloud-specific: the A64FX is a different
architecture (Arm SVE, HBM2) and x86_64 binaries won't run there. Show the top
result's breadcrumb and a short excerpt, and note whether it came from vector
search or BM25 keyword fallback (the leading `[search_method: bm25]` marker).

---

## Step 4 — Filesystem

Call `fs_ls(".")` to list the user's home directory. Show it cleanly and
highlight anything interesting (e.g. past job scripts under `agent/jobs/`).

Then demonstrate a safe round trip:
1. `fs_mkdir("agent/demo")`
2. `fs_ls("agent")` — show the new directory
3. `fs_checksum` on any file you copy in, to show integrity verification

---

## Step 5 — Recent jobs

Call `get_job_statuses([])` (empty list = last ~2 days).

If there are jobs, show a table: job ID | name | state | partition | elapsed.
Highlight any FAILED jobs and offer to investigate (wrong arch, missing module,
OOM). If there are none, say so and move on.

---

## Step 6 — Test job

Pick a CPU partition with idle nodes from Step 2 (fall back to `genoa`). Tell the
user you'll submit a quick test job, then submit via `submit_job`:
```json
{
  "name": "cloud-demo",
  "executable": "module load system/genoa mpi/openmpi-x86_64 && hostname && uname -m && nproc",
  "resources": {"node_count": 1, "processes_per_node": 1},
  "attributes": {"duration": 300, "queue_name": "genoa"}
}
```
Show the job ID and script path.

---

## Step 7 — Monitor and read output

Poll `get_job_statuses([<id>])` every ~15 s (wait ~15 s before the first poll —
sacct lags submit by a second or two). Stop when the state is `completed` or
`failed` (or after ~5 polls). Once completed, `fs_tail(<workdir>/slurm-<id>.out)`
and show the output — it should contain the node hostname, the arch, and a CPU count.

---

## Closing

Summarize in four bullets: facility + live status checked, docs searched,
filesystem exercised, a CPU job submitted and its output retrieved. Then invite
the user to target any hardware family via `/rccs-cloud-submitting-jobs`.
