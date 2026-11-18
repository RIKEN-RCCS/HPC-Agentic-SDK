This is a heterogeneous ~20-partition cluster, so pick a partition with
idle nodes from Step 2 rather than assuming one. A CPU partition such as
`genoa` is the least contended choice for a quick demo; only use a GPU
partition if the user specifically wants to see one.

Remember every batch script needs its partition's own `system/<partition>`
module loaded first — `source /etc/profile` is emitted for you. A spec that
works on `genoa`:

```json
{
  "name": "cloud-demo",
  "executable": "module load system/genoa && hostname && lscpu | head -20",
  "resources": {"node_count": 1, "processes_per_node": 1},
  "attributes": {"duration": 300, "queue_name": "genoa"}
}
```

There is no default partition here — `attributes.queue_name` must be set.
