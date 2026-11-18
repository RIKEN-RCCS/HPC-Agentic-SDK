---
name: rccs-cloud-remote-command
description: Use when the user wants to run one or more shell commands on R-CCS Cloud's login node, or when another workflow needs run_command_on_cluster for a live check not covered by a safer typed tool. Requires an exact command preview and explicit user permission before execution.
user-invocable: true
---

# Running login-node commands on R-CCS Cloud

Every call in this skill uses `facility="rccs-cloud"`.
`run_command_on_cluster` is an escape hatch: it can do anything the user's
login shell can do and bypasses the typed tools' validation and deletion
guards. Use a specific tool such as `fs_view`, `get_resources`, or
`submit_job` whenever one fits.

## Before running anything: sketch, show, ask, and wait

Before **every** `run_command_on_cluster` call or approved sequence:

1. Sketch the proposed work in plain language.
2. Show each exact command in a numbered list, including the facility.
3. State whether the commands are read-only and name any files, jobs, or
   configuration they may change.
4. Ask for explicit permission and wait for the user's answer. A general
   request such as "investigate the build" is not permission for commands
   the user has not seen. Permission covers only the commands shown; preview
   and ask again before adding or materially changing one.

Use wording like this:

> I propose three short, read-only checks on R-CCS Cloud:
>
> 1. `pwd` — confirm the login directory.
> 2. `uname -m` — identify the login node architecture.
> 3. `df -h .` — inspect free space on the current filesystem.
>
> These commands will not modify files or submit/cancel jobs. May I run these
> commands on R-CCS Cloud?

Do not execute the commands in the same response as that question. Wait for
the user to approve them.

## Prefer several short commands

Prefer multiple focused calls over one long shell program joined with many
`;`, `&&`, or `||` operators. Run them in order and inspect each result before
continuing. This makes failures attributable, keeps the user's approval
meaningful, and avoids later steps running on a false assumption.

A short pipeline that performs one coherent observation is fine, such as
`module -t avail 2>&1 | head -40`. A tightly coupled operation may also use
one small compound command, such as `cd project && make test`, when splitting
it would change its meaning.

Each call starts a fresh login shell in `$HOME`: working-directory changes,
loaded modules, shell variables, and activated environments do **not** persist
to the next call. Use explicit paths or repeat the minimal setup in a later
command. If a workflow genuinely needs a long stateful script or heavy
computation, create and submit a job instead of running it on the login node.
Files a command sequence needs (uploads, source trees, outputs) live under
`~/agent/work/…`, never in the home-directory root.

## Git-over-SSH authentication failures

When a remote `git` command fails with an SSH authentication error such as
`Permission denied (publickey)`, do not guess that SSH agent forwarding is
enabled or that a key has a conventional filename. Do not copy a private key
to the cluster, run `ssh-add`, ask for a passphrase, or make any remote-side
change.

First inspect the **local** resolved SSH configuration for the facility's
configured `ssh.host` with `ssh -G <host>` (a read-only local check). Use its
`forwardagent` and `identityfile` results to explain the next step:

- If `forwardagent` is `no`, explain that the cluster connection is not
  forwarding the user's local SSH agent. Ask whether they want to enable
  `ForwardAgent yes` for that facility's SSH alias; do not change it unless
  they approve.
- If `forwardagent` is `yes`, ask the user to run `ssh-add -l` locally. If
  the identity registered with **this facility** is absent, they should add
  the matching private key with `ssh-add <their-facility-key>`. Treat any
  resolved `identityfile` entries only as hints; never invent a path such as
  `~/.ssh/id_ed25519`.

After the user confirms the local agent is ready, retry the original Git
command. If a multiplexed SSH master was opened before forwarding was enabled,
ask the user to restart that master first. These checks and repairs happen on
the user's computer, not the cluster.

## After running: report what actually happened

Give the user a compact execution sketch based on the real outputs, including
what ran, the important result, and what changed. Do not merely paste raw
terminal output.

For example:

> Done on R-CCS Cloud:
>
> - Confirmed the login directory is `/home/alice`.
> - Confirmed the login node is `aarch64`.
> - The current filesystem has 420 GiB available.
> - Changed state: none. No files were written and no jobs were submitted.

If a command fails, say which command failed and stop before dependent steps.
Explain the failure and propose any new command separately; show it and ask
permission before running it.

Never expose secrets in a command or its recap. For destructive or otherwise
irreversible commands, identify the exact targets and consequences especially
clearly; prefer the guarded typed tool when one exists.
