HBW2 is CPU-first, so demo the default `mpc` partition (312 nodes, the
least contended) rather than the small GPU subsystem:

```json
{
  "name": "hokusai-demo",
  "executable": "hostname && echo '---' && lscpu | head -20",
  "resources": {"node_count": 1, "processes_per_node": 1},
  "attributes": {"duration": 300, "queue_name": "mpc"}
}
```

`queue_name` and `account` are both filled in automatically from the
configured defaults if omitted — but Step 1's `get_projects` output is worth
showing either way, since **fair-share standing is what determines queue
order here**.

Don't be alarmed if `get_resources` shows `mpc` at 0 idle nodes: HBW2
backfills aggressively, and a short job typically starts within seconds
anyway (verified — a 1-node job and even a 64-node job each started
immediately against a fully-allocated partition). Report what the job
actually does rather than predicting a long wait from the idle count.
