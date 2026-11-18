**Fugaku compute is billed against a project's node-hour allocation, and
the `f-pt` resource group additionally consumes Fugaku Points.** A
`mode="live"` (or `"lazy"` on a cache miss) run of a cell containing
`submit_job` spends real allocation — tell the user which group and
resource group will be charged before running that cell.

Pin `attributes.account` (the project group) and `attributes.queue_name`
explicitly in the notebook's spec rather than relying on configured
defaults: a notebook meant to be reproducible by someone else shouldn't
silently charge whichever group *their* config names, and resource-group
availability differs per project.
