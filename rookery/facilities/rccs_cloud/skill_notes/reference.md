The R-CCS Cloud is a **heterogeneous research testbed** — its point is
that partitions differ in hardware, OS, and toolchain. Almost every
question about it has a "which partition?" qualifier; ask for one if the
user hasn't given it.

### Orientation (stable facts — prefer live tools for anything current)

- **Partition families**: CPU-only (`fx700`, `genoa`, `genoa-m`, `r340`),
  NVIDIA GPU (`a100`, `b300`, `ai-*`, `qc-a100`, `qc-h100`, `qc-gh200`,
  `ng-dgx`), AMD GPU (`mi100`, `qc-mi250`, `fs-mi300*`), Intel GPU
  (`qc-pvc`). Pick the partition for the hardware you need.
- **Modules are partition-specific**: each partition has a
  `system/<partition>` module that must be loaded first. Never use a
  module from the wrong partition — it produces wrong-ABI segfaults, not a
  clean error.
- **GPU flag**: most GPU partitions use `--gpus=<n>` (set
  `resources.gpus`); the exceptions are `qc-gh200` and `ng-dgx-m[0-3]`
  (unified CPU+GPU superchips — no flag at all).
- **Architectures**: `fx700` is A64FX (aarch64); `qc-gh200` and `ng-dgx`
  are NVIDIA Grace (aarch64); everything else is x86_64. Cross-compile for
  fx700 on `r340`.
- **OS**: `ng-dgx-m[0-3]` runs Ubuntu; every other partition runs Rocky
  Linux. A wheel built for one may need rebuilding for the other.
- **Login**: `login.cloud.r-ccs.riken.jp`, key-based SSH.
- **`source /etc/profile`** must precede any module command in a batch
  script — the plugin emits it automatically, so don't add it yourself.
- **Known restrictions** (verify live, these change): `ai-h100l` is
  team-restricted — use `ai-h100l-pu`, which caps at 30 minutes;
  `qc-h100` has been under repair; `qc-mi210` GPUs were still being set up.
- **No project account is needed** — jobs without `--account` use the
  user's default Slurm account.

### Getting help

If neither the guide nor the tools answer it, point the user at the R-CCS
Cloud portal or its support contact.
