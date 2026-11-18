   - An alias in `~/.ssh/config` (recommended) → `"host": "<alias>"`,
     pointing at `hokusai.riken.jp`.
   - **Key-based auth is the only way onto HBW2** — there are no password
     prompts. If the key isn't registered yet, register the public key
     through the HBW2 portal at `https://hokusai.riken.jp/hbw2/` before the
     first login.

**Also set `defaults.account`** — this facility needs a second key that
most don't:

```json
{
  "ssh": { "host": "hokusai" },
  "defaults": { "account": "RB99999" }
}
```

**Every HBW2 job must be billed to a project**, so set this (or pass an
account per job) or submissions will error with a message telling you to.
RIKEN project IDs start `RB`; HPCI-derived ones start `HP`. Use
`get_projects(facility="{{SLUG}}")` to see which accounts you may charge.
`{{ENV_PREFIX}}_ACCOUNT` overrides the file. A legacy top-level `"account"`
key (from an older config example) is still honored if `defaults.account`
is absent, so an existing config keeps working unchanged.
