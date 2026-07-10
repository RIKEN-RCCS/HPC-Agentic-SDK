---
name: hokusai-demo
description: Interactive demo of the HOKUSAI BigWaterfall2 (HBW2) plugin — walks through facility info, live cluster status, projects, job submission, and output retrieval on the RIKEN HOKUSAI BigWaterfall2 (HBW2) supercomputer. User-invocable with /hokusai-demo.
user-invocable: true
---

# HOKUSAI (HBW2) demo

Run each step in order — actually call the tools, don't just describe the
plan. Present results as a readable narrative, not raw JSON dumps. Pause
after each step and show the output before moving on.

---

## Step 1 — Confirm it's configured

Call `get_facility` — it needs no SSH and returns HBW2's static facts. If it
returns the facility JSON, config parsing works. Then call `get_projects` to
prove SSH + accounting are reachable, and show which projects can be billed.
If either errors with "Plugin not configured," switch to the
**hokusai-configuring** skill instead of continuing.

## Step 2 — Live cluster status

Call `get_resources`. For each partition (mpc, mpc_l, lmc, gpu) show a mini
utilization bar:

```
mpc   ████████░░  28/312 idle
```

(Use █ for allocated, ░ for idle, scaled to ~10 chars; add the idle count in
plain text.) Point out which partition has the most idle capacity right
now — that's where a job would start soonest.

## Step 3 — Submit a tiny job

Tell the user you'll submit a quick test job, then call `submit_job`:

```json
{
  "name": "hokusai-demo",
  "executable": "echo 'hello from HBW2'; hostname; sleep 20",
  "resources": {"node_count": 1, "processes_per_node": 1, "cpu_cores_per_process": 1},
  "environment": {"OMP_NUM_THREADS": "1"},
  "attributes": {"duration": "00:03:00", "queue_name": "mpc"}
}
```

(`attributes.account` is left unset — it defaults to the configured
project.) Use `render_job_script` first only if the user wants to see the
exact sbatch script before it runs. Show the returned job ID and script
path.

## Step 4 — Monitor

Poll `get_job_status(job_id)` every ~15 seconds until the state reaches
`completed` (queued → active → completed), stopping after ~5 polls if it's
still queued — tell the user to check back with `get_job_status` themselves
in that case. Explain the wait reason if one is reported while queued.

## Step 5 — Read the output

Call `read_job_output(job_id)` — it prints the `slurm-<jobid>.out` log. The
user should see the `hello from HBW2` line and the compute node's hostname.

---

## Closing

Summarize in four bullets: configuration + facility + live status checked,
a project confirmed billable, a CPU job submitted and monitored, and its
output retrieved. Then invite the user to submit real work via
`/hokusai-submitting-jobs` or monitor existing jobs via
`/hokusai-monitoring-jobs`.
