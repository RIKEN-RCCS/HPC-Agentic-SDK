## Worth knowing before demoing Fugaku

**Step 1 does show projects.** `get_projects` derives the project groups
from `id -Gn`, excludes the unusable shared `fugaku` group, and reports each
group's usable resource groups. It also includes a Fugaku Points summary
when the group has point accounting. Use
`get_project_allocations(facility="{{SLUG}}", project_id="<group>")` when
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
