---
name: fugaku-demo
description: Interactive demo of Fugaku — walks through configuration, facility info, live cluster status, docs search, filesystem access, and a real job end to end.
user-invocable: true
---

# Fugaku demo

Run each step in order — actually call the tools, don't just describe the
plan. Present results as a readable narrative, not raw JSON dumps. Use
markdown headers and tables to make it scannable. Pause after each step and
show the output before moving on. Every tool call uses `facility="fugaku"`.

## Step 1 — Confirm it's configured

Call `get_facility(facility="fugaku")` — it needs no SSH and returns this
machine's static facts, so a good result proves config parsing works.
Summarize the partitions, storage tiers, and modules.

Then call `get_projects(facility="fugaku")` to prove SSH is actually
reachable, and show which projects can be billed.

**If either call reports that the facility isn't configured, stop the demo
and switch to the `fugaku-configuring` skill.** The error itself contains
the full setup directions for this machine — walk the user through those
rather than continuing.

## Step 2 — Live cluster status

Call `get_resources(facility="fugaku")`. Show a table of partitions with
allocated/idle/total nodes, and point out where a job would start soonest.

## Step 3 — Documentation search

Call `search_docs(facility="fugaku", query="how do I submit a job")` on
the `hpc-docs` server. Show the top result and cite its section breadcrumb.

## Step 4 — Filesystem

Call `fs_ls(facility="fugaku", path=".")` to show the top of the user's
home directory on this machine.

## Step 5 — Recent jobs

Call `get_job_statuses(facility="fugaku", job_ids=[])` (an empty list
means "the last ~2 days"). If there are jobs, show them as a table: job ID,
name, state, partition, elapsed — and highlight any failed ones, offering to
investigate. If there are none, say so and move on.

## Step 6 — Submit a test job

Tell the user you'll submit a short test job to verify end-to-end
submission, then call `render_job_script(facility="fugaku", spec=...)` to
show exactly what will run, then `submit_job` with the same spec. Show the
returned job ID and script path. See the facility notes below for a spec
that suits this machine.

## Step 7 — Monitor and read the output

Poll `get_job_status(facility="fugaku", job_id=...)` every ~15 seconds —
use `run_command_on_cluster(facility="fugaku", command="sleep 15")` as the
wait, since there's no sleep tool. Stop when the state is terminal, or after
about five polls (tell the user to check back later if it's still queued).

Once it finishes, read the output: take `meta_data.workdir` from the final
status and call
`fs_tail(facility="fugaku", path="<workdir>/slurm-<job_id>.out")`. Don't
assume the home directory — a job that set `directory` writes its output
there instead.

## Closing

Summarize in four bullets: configuration and facility checked, live status
seen, a job submitted and monitored, and its output retrieved. Then invite
the user to submit real work via `/fugaku-submitting-jobs`, monitor
existing jobs via `/fugaku-monitoring-jobs`, or ask about the machine via
`/fugaku-reference`.

## Facility notes for this demo

## Worth knowing before demoing Fugaku

**Step 1 does show projects.** `get_projects` derives the project groups
from `id -Gn`, excludes the unusable shared `fugaku` group, and reports each
group's usable resource groups. It also includes a Fugaku Points summary
when the group has point accounting. Use
`get_project_allocations(facility="fugaku", project_id="<group>")` when
you need the full point balance for a listed group; `trial` deliberately has
no point row and can use only `spot-*` resource groups.

**Step 2's `get_resources` returns raw `pjstat --rsc` text**, not structured
occupancy — say so rather than presenting it as a partition table.

For Step 6, `attributes.queue_name` is required (no default) and a project
group must be configured. A minimal validation job:

```json
{
  "name": "fugaku-demo",
  "executable": "hostname && lscpu | head -20",
  "resources": {"node_count": 1},
  "attributes": {"duration": 300, "queue_name": "small"}
}
```

If the account's group is `trial`, use a `spot-*` resource group instead —
`small` will be rejected.

For Step 7, read `<name>.<job_id>.out` in the submission directory — and
remember `completed` here only means the scheduler finished, so actually
show the output rather than declaring success from the state alone.
