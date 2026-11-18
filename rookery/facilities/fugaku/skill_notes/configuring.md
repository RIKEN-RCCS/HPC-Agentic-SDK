   - An alias in `~/.ssh/config` (recommended) → `"host": "<alias>"`,
     pointing at your Fugaku login node via RIKEN's login gateway.
   - **Key-based SSH only.**

**Also set `defaults.group`** — Fugaku needs a second key that most
facilities don't:

```json
{
  "ssh": { "host": "fugaku" },
  "defaults": { "group": "hp000000", "gfscache_volume": "/vol0004" }
}
```

- `defaults.group` is the project group charged on every job (`#PJM -g`).
  **Mandatory**: the shared `fugaku` group that every account belongs to is
  explicitly denied job submission, so there is no usable fallback. Run
  `id` on the login node to see the account's real project groups.
  `{{ENV_PREFIX}}_GROUP` overrides the file.
- `defaults.gfscache_volume` (e.g. `/vol0004`) declares the second-layer
  storage volume a job will touch. Required whenever work goes outside
  `$HOME`, including anything under Spack; omit it for jobs that stay in
  `$HOME`. `{{ENV_PREFIX}}_GFSCACHE` overrides the file.
- **Resolve the group's data area at setup time.** Run `accountd -E` on
  the login node once the connection works: it lists each project group's
  `/vol0X0X/data/<group>/` path and quota. That output is the checked
  answer for which volume `gfscache_volume` should name, and jobs should
  run from that data area, not `$HOME` (see `fugaku-submitting-jobs`).
