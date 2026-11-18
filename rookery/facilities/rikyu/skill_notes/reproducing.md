**RIKYU compute is billed with no usage cap.** A `mode="live"` (or
`"lazy"` on a cache miss) run of a cell containing `submit_job` submits a
real, billed job — tell the user what will be submitted before running
that cell for real, the same as you would outside this workflow.
