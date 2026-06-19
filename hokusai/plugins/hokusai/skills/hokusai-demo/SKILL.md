---
name: hokusai-demo
description: Interactive demo of HokusaiAgent — walks through facility info, live cluster status, docs search, filesystem access, and CPU job submission on HOKUSAI BigWaterfall2 (HBW2). User-invocable with /hokusai-demo.
---

# HokusaiAgent demo

Run each step in order. Present results as a readable narrative — not raw JSON dumps. Use markdown headers and tables to make it scannable. Pause after each step and show output before moving on.

---

## Step 1 — Facility overview

Call `get_facility`. Present the key facts as a short table:
- Subsystems: MPC / LMC / GPU — node count, CPU, memory per node
- Partitions: name → max nodes, max cores, memory/node, max wall time (one row each)
- Storage tiers (home, data, /tmp_work)

Lead with one sentence: **"HOKUSAI BigWaterfall2 is RIKEN's CPU-first supercomputer — 312 Intel Xeon MPC nodes plus a large-memory server, with a small 4-node H100 GPU server for postprocessing."**

---

## Step 2 — Live cluster status

Call `get_resources`. For each partition, show a mini utilization bar:

```
mpc    ████████░░  250/312 nodes busy
mpc_l  ███░░░░░░░   2/156 busy
...
```

(Use █ for allocated, ░ for idle, scaled to ~10 chars. Add the idle count in plain text.)

Point out which partitions have the most idle nodes right now — that's where a job would start fastest.

---

## Step 3 — Documentation search

Call `search_docs` with a practical question a new user would actually ask, e.g. *"how do I submit an MPI batch job?"* or *"what compilers are available?"*.

Show the top result: the breadcrumb, a short excerpt, and the source. Note whether the result came from vector search or BM25 keyword matching (the `method` field). If `vector`, say: *"Semantic search is active — results are ranked by meaning via the shared RIKEN BGE-M3 endpoint."* If `bm25`, say: *"Running on BM25 keyword search (no embedding API key set, or off the RIKEN network) — still works fully offline."*

---

## Step 4 — Filesystem

Call `fs_ls(".")` to list the user's home directory. Show the listing cleanly (just names, sizes, dates — no raw flag noise). Highlight anything interesting: job scripts in `.hokusai/jobs/`, `/data` symlinks, project directories.

Then demonstrate the filesystem tools:
1. `fs_upload("/tmp/hokusai-demo.txt", "hello from HokusaiAgent\n")` — write a file
2. `fs_checksum("/tmp/hokusai-demo.txt")` — show the SHA-256
3. `fs_cp("/tmp/hokusai-demo.txt", "/tmp/hokusai-demo-copy.txt")` then `fs_checksum` — confirm the checksum matches

Present this as: *"Upload, checksum, copy — the filesystem toolkit."*

---

## Step 5 — Recent jobs

Call `get_job_statuses([])` (empty list = last 2 days).

If there are jobs, show them as a table: job ID | name | state | partition | elapsed. Highlight any FAILED jobs and offer to investigate.

If there are no recent jobs, say so and move straight to Step 6.

---

## Step 6 — Test job

Tell the user: *"Let's submit a quick CPU test job to verify end-to-end submission and output."* (If you know the user's project ID, set `account`; otherwise the configured default is used.)

Submit via `submit_job` with this spec:
```json
{
  "name": "hokusai-demo",
  "executable": "hostname && echo '---' && lscpu | grep -E 'Model name|Socket|Core|Thread' && echo '---' && free -h",
  "resources": {"node_count": 1, "processes_per_node": 1},
  "attributes": {"duration": 300, "queue_name": "mpc"}
}
```

Show the user the rendered job ID and script path. Then call `get_job_status(<job_id>)` immediately and report the initial state + queue reason if present.

---

## Step 7 — Monitor and read output

Poll `get_job_status` once every ~15 seconds (use `run_command_on_cluster("sleep 15")` as the wait). Stop when state is `completed` or `failed` (or after 5 polls — tell the user to check back with `get_job_status` if it's still queued).

Once completed, call `fs_tail(<workdir>/slurm-<job_id>.out)` and show the output. It should report the node hostname and an Intel Xeon CPU — confirm the CPU model matches what `get_facility` reported for MPC.

---

## Closing

Summarize what just happened in 5 bullet points:
- Facility and live cluster status checked
- Documentation searched
- Filesystem explored with upload, checksum, and copy
- A CPU job submitted, ran, and its output (Intel Xeon node info) retrieved
- Everything went through one SSH layer to the HBW2 front-end

Then say: *"From here you can submit real workloads with /hokusai-submitting-jobs, monitor them with /hokusai-monitoring-jobs, or ask anything about the cluster."*
