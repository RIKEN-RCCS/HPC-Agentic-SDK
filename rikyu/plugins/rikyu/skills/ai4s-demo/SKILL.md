---
name: ai4s-demo
description: Interactive demo of RikyuAgent — walks through facility info, live cluster status, docs search, filesystem access, and job submission on the RIKEN AI4S supercomputer. User-invocable with /ai4s-demo.
---

# RikyuAgent demo

Run each step in order. Present results as a readable narrative — not raw JSON dumps. Use markdown headers and tables to make it scannable. Pause after each step and show output before moving on.

---

## Step 1 — Facility overview

Call `get_facility`. Present the key facts as a short table:
- Hardware: GPU model, CPU architecture, node count
- Partitions: name → GPUs/node, CPUs/node, max wall time (one row per partition)
- Storage tiers (home, scratch, any project storage)

Lead with one sentence: **"The AI4S supercomputer at RIKEN is an NVIDIA GB200 cluster running <N> nodes."**

---

## Step 2 — Live cluster status

Call `get_resources`. For each partition, show a mini utilization bar:

```
1n1gpu  ████████░░  80/100 nodes busy
1n2gpu  ███░░░░░░░  30/100 idle
...
```

(Use █ for allocated, ░ for idle, scaled to ~10 chars. Add the idle count in plain text.)

Point out which partitions have the most idle nodes right now — that's where a job would start fastest.

---

## Step 3 — Documentation search

Call `search_docs` with a practical question a new user would actually ask, e.g. *"how do I submit a batch job?"* or *"what storage is available?"*.

Show the top result: the breadcrumb, a short excerpt, and the URL. Then note whether the result came from vector search or BM25 keyword fallback (the `method` field) — if vector, say: *"Semantic search is active — results are ranked by meaning, not just keyword matches."*

---

## Step 4 — Filesystem

Call `fs_ls(".")` to list the user's home directory. Show the listing cleanly (just names, sizes, dates — no raw flag noise). Highlight anything interesting: job scripts in `.rikyu/jobs/`, scratch symlinks, project directories.

Then demonstrate the new filesystem tools:
1. `fs_cp(".rikyu/jobs/<most recent script>", "/tmp/demo-copy.sh")` — copy the most recent job script
2. `fs_checksum("/tmp/demo-copy.sh")` — show the SHA-256
3. `fs_mv("/tmp/demo-copy.sh", "/tmp/demo-renamed.sh")` — rename it, note this is destructive
4. `fs_checksum("/tmp/demo-renamed.sh")` — confirm the checksum matches (same file)

Present this as: *"Copy, checksum, move — the full filesystem toolkit."*

---

## Step 5 — Recent jobs

Call `get_job_statuses([])` (empty list = last 2 days).

If there are jobs, show them as a table: job ID | name | state | partition | elapsed. Highlight any FAILED jobs and offer to investigate.

If there are no recent jobs, say so and move straight to Step 6.

---

## Step 6 — Test job

Tell the user: *"Let's submit a quick 5-minute test job to verify end-to-end submission and output."*

Submit via `submit_job` with this spec:
```json
{
  "name": "rikyu-demo",
  "executable": "hostname && echo '---' && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader",
  "resources": {"node_count": 1, "gpus_per_node": 1, "processes_per_node": 1},
  "attributes": {"duration": 300, "queue_name": "1n1gpu"}
}
```

Show the user the rendered job ID and script path. Then call `get_job_status(<job_id>)` immediately and report the initial state + queue reason if present.

---

## Step 7 — Monitor and read output

Poll `get_job_status` once every ~15 seconds (use `run_command_on_cluster("sleep 15")` as the wait). Stop when state is `completed` or `failed` (or after 5 polls — tell the user to check back with `get_job_status` if it's still queued).

Once completed, call `fs_tail(<workdir>/slurm-<job_id>.out)` and show the output. It should contain the node hostname and GPU info — confirm the GPU model matches what `get_facility` reported.

---

## Step 8 — Container job

Tell the user: *"Now let's run the same job inside a Singularity container — this is how you bring your own software environment to the cluster."*

Check whether `$HOME/ubuntu-22.04.sif` exists with `fs_stat("~/ubuntu-22.04.sif")`. If it doesn't, skip this step and note that a `.sif` file is needed first (pull with `singularity pull`).

If it exists, submit via `submit_job`:
```json
{
  "name": "rikyu-demo-container",
  "executable": "cat /etc/os-release && uname -m",
  "resources": {"node_count": 1, "gpus_per_node": 1},
  "attributes": {"duration": 300, "queue_name": "1n1gpu"},
  "container": {
    "image": "$HOME/ubuntu-22.04.sif"
  }
}
```

Poll to completion, then `fs_tail` the output. Point out:
- The OS name comes from *inside* the container (Ubuntu), not from the host (RHEL/Rocky)
- The architecture is still `aarch64` — the container runs natively on Grace
- GPU passthrough (`--nv`) was added automatically because the job requested GPUs

Say: *"The same spec works with any Singularity-compatible image — docker:// URIs, NGC containers, or a .sif you built yourself."*

---

## Closing

Summarize what just happened in 5 bullet points:
- Facility and live cluster status checked
- Documentation searched with semantic vector search
- Filesystem explored with copy, checksum, and move
- Bare-metal job submitted, ran, GPU output retrieved
- Container job ran inside Ubuntu on the same GB200 hardware

Then say: *"From here you can submit real workloads with /ai4s-submitting-jobs, monitor them with /ai4s-monitoring-jobs, or ask anything about the cluster."*
