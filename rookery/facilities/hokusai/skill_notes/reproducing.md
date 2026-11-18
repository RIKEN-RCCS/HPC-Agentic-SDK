**Every HBW2 job is billed to a project under a fair-share budget.** A
`mode="live"` (or `"lazy"` on a cache miss) run of a cell containing
`submit_job` spends real core-time against that project — tell the user
which account will be charged before running that cell for real.

Pin `attributes.account` explicitly in the notebook's spec rather than
relying on the configured default: a notebook meant to be reproducible by
someone else shouldn't silently bill whichever project *their*
`~/.hpc-agent/hokusai.json` happens to name.
