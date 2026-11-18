Use this spec for Step 6 — it proves the GPU allocation actually worked,
not just that a job ran:

```json
{
  "name": "rikyu-demo",
  "executable": "hostname && echo '---' && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader",
  "resources": {"gpus": 1, "processes_per_node": 1},
  "attributes": {"duration": 300, "queue_name": "gpu"}
}
```

When the output comes back, confirm the reported GPU model matches what
`get_facility` said — that's the check that makes this demo meaningful.

If the user belongs to several RIKYU projects, `submit_job` will be
rejected unless an account is set; `get_projects` in Step 1 already showed
which ones are available, so add `"account": "<project>"` to `attributes`.

Optional follow-up if the user wants to see containers: rerun the same
command inside Singularity by setting `container.image` — the GPU
passthrough flag (`--nv`) is added automatically when the job requests GPUs.
