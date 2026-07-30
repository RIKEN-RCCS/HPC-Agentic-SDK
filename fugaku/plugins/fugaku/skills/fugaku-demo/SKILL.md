---
name: fugaku-demo
description: Demonstrate Fugaku Agent end-to-end — facility info, live status, docs search, filesystem access, and job submission.
user-invocable: true
---

# Fugaku Agent demo

Run each step in order — actually call the tools, don't just describe the
plan. Present results as a readable narrative, not raw JSON dumps. Pause
after each step and show the output before moving on.

## Step 1 — Facility info

Call `get_facility`. Point out that Fugaku is CPU-only (A64FX, no GPUs),
scheduled by PJM (`pjsub`/`pjstat`/`pjdel`), and summarize the resource
groups.

## Step 2 — Live status

Call `get_resources`. Note that this returns raw `pjstat --rsc`/`pjshowrsc`
text (best-effort — these commands didn't expose structured per-partition
occupancy during this port's testing), then call
`run_command_on_cluster("id")` to show the real project groups available.

## Step 3 — Docs search

Call `search_docs` for `"layered storage LLIO gfscache"` and summarize the
top result in your own words.

## Step 4 — Filesystem

Call `fs_ls` on `.` (the home directory) to show the live connection.

## Step 5 — Submit a real job

Tell the user you'll submit a tiny one-node job on the `small` resource
group (using their configured default project group), then call
`submit_job` with a spec like:

```json
{
  "name": "fugaku-demo",
  "executable": "hostname && echo PJM_JOBID=$PJM_JOBID",
  "attributes": {"duration": 300, "queue_name": "small"},
  "resources": {"node_count": 1}
}
```

Poll with `get_job_status` until it leaves QUEUED/ACTIVE, then `fs_tail`
the job's `<name>.<job_id>.out` file under `~/agent/jobs/` to show the
real output.
