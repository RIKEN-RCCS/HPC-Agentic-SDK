**R-CCS Cloud has no single default partition** — a submit_job cell in the
notebook must set `attributes.queue_name` explicitly, and the module-load
line in `executable` must match that partition (see
`rccs-cloud-submitting-jobs`'s module table). Don't reuse a script from one
partition on another without checking the module line.
