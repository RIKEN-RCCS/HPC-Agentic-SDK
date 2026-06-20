---
name: rccs-cloud-demo
description: Interactive demo of RCCS-CloudAgent — walks through facility info, live cluster status, docs search, filesystem access, and job submission on the RIKEN R-CCS Cloud. User-invocable with /rccs-cloud-demo.
user-invocable: true
---

# RCCS-CloudAgent demo

Run each step in order. Present results as a readable narrative — not raw JSON dumps. Use markdown headers and tables to make it scannable. Pause after each step and show output before moving on.

---

## Step 1 — Facility overview

Call `get_facility`. Present the key facts:
- One sentence leading with what the R-CCS Cloud is: a heterogeneous research testbed with many partition families.
- A table grouping partitions by hardware family: CPU-only | NVIDIA GPU | AMD GPU | Intel GPU — with columns: partition name, node count, key hardware, module command.
- Note the special cases: ai-h100l-pu (30 min max), qc-h100 (under repair), qc-mi210 (GPU in progress), ng-dgx (Ubuntu).

---

## Step 2 — Live cluster status

Call `get_resources`. For each partition, show a mini utilization bar:

```
genoa     ████░░░░░░  6/16 nodes busy
qc-gh200  ██░░░░░░░░  2/8 idle
...
```

(Use █ for allocated, ░ for idle, scaled to ~10 chars. Add the idle count in plain text.)

Point out which partitions have idle capacity right now — those are where a job would start fastest.

---

## Step 3 — Documentation search

Call `search_docs` with a question a new user would ask, e.g. *"what modules do I need to load for the genoa partition?"* or *"how do I request GPUs?"*

Show the top result: the breadcrumb, a short excerpt, and the URL. Note whether results came from vector search or BM25 keyword fallback (the `method` field).

---

## Step 4 — Filesystem

Call `fs_ls(".")` to list the user's home directory. Show the listing cleanly. Highlight anything interesting: job scripts in `.rccs-cloud/jobs/`.

Then demonstrate:
1. `fs_cp(".rccs-cloud/jobs/<most recent script>", "/tmp/demo-copy.sh")` — copy the most recent job script (skip gracefully if none exist)
2. `fs_checksum("/tmp/demo-copy.sh")` — show the SHA-256
3. `fs_mv("/tmp/demo-copy.sh", "/tmp/demo-renamed.sh")` — rename it
4. `fs_checksum("/tmp/demo-renamed.sh")` — confirm checksum matches

---

## Step 5 — Recent jobs

Call `get_job_statuses([])` (empty list = last 2 days).

If there are jobs, show them as a table: job ID | name | state | partition | elapsed. Highlight any FAILED jobs and offer to investigate — note which partition they ran on and whether the failure mode matches known issues (wrong arch, missing module, OOM).

If there are no recent jobs, say so and move to Step 6.

---

## Step 6 — Test job (CPU)

Tell the user: *"Let's submit a quick test job to genoa — the general-purpose CPU partition."*

Submit via `submit_job`:
```json
{
  "name": "cloud-demo",
  "executable": "module load system/genoa mpi/openmpi-x86_64 && hostname && uname -m && nproc",
  "resources": {"node_count": 1, "processes_per_node": 1},
  "attributes": {"duration": 300, "queue_name": "genoa"}
}
```

Show the job ID and script path. Call `get_job_status` immediately and report the initial state + queue reason if present.

---

## Step 7 — Monitor and read output

Poll `get_job_status` once every ~15 seconds (use `run_command_on_cluster("sleep 15")` as the wait). Stop when state is `completed` or `failed` (or after 5 polls).

Once completed, call `fs_tail(<workdir>/slurm-<job_id>.out)` and show the output. It should contain the node hostname, `x86_64`, and a CPU count.

---

## Closing

Summarize in 4 bullet points:
- Facility and live cluster status checked across all partition families
- Documentation searched (shows module requirements at a glance)
- Filesystem explored with copy, checksum, and move
- CPU job submitted on genoa, ran, output retrieved

Then say: *"From here you can target any hardware family — choose your partition with /rccs-cloud-submitting-jobs, or ask about a specific GPU partition to learn which modules and flags it needs."*
