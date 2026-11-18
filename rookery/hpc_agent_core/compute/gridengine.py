"""GridEngineBackend — qsub/qstat/qacct/qdel implementation (PLAN.md §3b).

Promoted from shinobulab-cell-cluster-mcp's cell2026_mcp/compute/gridengine.py
(the only Grid Engine machine in the family so far), adapted to fit here:
- res.gpus_per_node -> res.gpus (core's models.py field rename).
- The hardcoded ~/.cell2026/jobs/ path -> a jobs_dir constructor default of
  "agent/jobs" (matching SlurmBackend and PLAN.md §3e's visible-directory bias).
- cell2026's specific host-pinning quirk (helix/kinase are HOSTS on a
  single real queue, all.q, so "-q helix" is rejected and must become
  "-q all.q -l hostname=helix") is generalized into host_pins/queue_aliases/
  default_queue constructor params rather than hardcoded — this is a
  plausible recurring shape for small Grid Engine clusters (one real queue,
  node selection by host pin), not a cell2026-only quirk, so it's worth the
  small config surface. A second real GE machine may still need to subclass
  and override _resolve_queue if its shape genuinely differs (PLAN.md §2a/§2b).
- config.ge_bin_prefix() (an env-var override for non-login-shell test/CI
  environments) becomes a plain bin_prefix constructor argument — resolving
  it from an env var, if a machine wants that, is that machine's own
  config.py's job, not something baked into this backend.

GPU allocation note (from the original, PROBE-CONFIRMED on cell2026): GE's
RSMAP mechanism allocates a GPU index but does NOT set CUDA_VISIBLE_DEVICES
and applies no cgroup isolation. The allocated device is exposed as the
environment variable $SGE_HGR_gpu (space-separated for N>1); the rendered
script translates it to CUDA_VISIBLE_DEVICES. This is real, standard Grid
Engine RSMAP behavior, not cell2026-specific, so it's kept as unconditional
behavior here rather than a config knob.

NOT independently re-verified against a live Grid Engine cluster in this
promotion — it was already live-tested as part of shinobulab-cell-cluster-mcp
(see that repo's __reports__/cell2026_probe/), and the qstat/qacct parsing
and _header/_gpu_prologue logic are carried over intact; only the
integration points above changed. Confirm with a real job after repointing
a machine here, per the porting lessons (doctor/tests passing isn't the
same as a real job succeeding).
"""
from __future__ import annotations

import re
import shlex

from hpc_agent_core.compute.base import SchedulerBackend, duration_to_hms, render_body, to_epoch
from hpc_agent_core.middleware import norm_path, run_command, write_remote_file
from hpc_agent_core.models import Job, JobSpec, JobState, JobStatus, map_ge_state


class GridEngineBackend(SchedulerBackend):
    """Grid Engine (AGE/SGE) scheduler backend.

    Implements the five SchedulerBackend operations using
    qsub/qstat/qacct/qdel via the middleware SSH layer.
    """

    def __init__(self, facility: str, name: str = "gridengine", jobs_dir: str = "agent/jobs",
                 default_queue: str = "all.q", default_pe: str = "smp",
                 host_pins: set[str] | None = None,
                 queue_aliases: set[str | None] | None = None,
                 bin_prefix: str = ""):
        """
        default_queue: the real GE queue name to submit into.
        default_pe: parallel environment used when a JobSpec doesn't set one
            (JobAttributes.parallel_env already defaults to "smp" too).
        host_pins: hostnames that are really host-selectors on the single
            default_queue, not separate queues (qsub rejects "-q <host>"
            directly) — translated to "-q {default_queue} -l hostname=<host>".
        queue_aliases: queue_name values that mean "use default_queue, no
            host pin" (None and "" are always included).
        bin_prefix: prepended to qsub/qstat/qacct/qdel, for environments
            where the GE bin directory isn't already on PATH (a login shell,
            which middleware already uses, normally makes this unnecessary).
        """
        super().__init__(facility=facility, name=name)
        self._jobs_dir = jobs_dir
        self.default_queue = default_queue
        self.default_pe = default_pe
        self.host_pins = set(host_pins or ())
        self.queue_aliases = {None, "", default_queue} | set(queue_aliases or ())
        self.bin_prefix = bin_prefix

    def _resolve_queue(self, queue_name: str | None) -> tuple[str, str | None]:
        """Translate a JobSpec queue_name into a (qname, host) pair."""
        if queue_name in self.host_pins:
            return self.default_queue, queue_name
        if queue_name in self.queue_aliases:
            return self.default_queue, None
        return queue_name, None  # forward-compat: a real, distinct queue

    def _qbin(self, cmd: str) -> str:
        prefix = self.bin_prefix
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        return prefix + cmd

    def _header(self, spec: JobSpec) -> str:
        """Build the #$ directive block for a GE batch script.

        Returns a string starting with the shebang and ending with a
        trailing newline (no blank line — caller adds the GPU prologue + body).
        """
        res = spec.resources
        attrs = spec.attributes

        qname, host = self._resolve_queue(attrs.queue_name)
        pe = attrs.parallel_env or self.default_pe

        # Slots = total parallel processes (processes_per_node × node_count or
        # process_count). GE has no multi-node concept here; slots controls
        # thread/process count for the PE.
        slots = res.process_count if res.process_count is not None else res.processes_per_node * res.node_count

        hms = duration_to_hms(attrs.duration)

        lines: list[str] = [
            "#!/bin/bash",
            f"#$ -N {spec.name}",
            f"#$ -q {qname}",
        ]
        if host:
            lines.append(f"#$ -l hostname={host}")

        if spec.directory:
            # Grid Engine's -wd is not shell-evaluated either — same fix as
            # SlurmBackend's --chdir, see that comment.
            lines.append(f"#$ -wd {norm_path(spec.directory)}")
        else:
            lines.append("#$ -cwd")

        stdout = norm_path(spec.stdout_path or f"~/{self._jobs_dir}/{spec.name}.o")
        stderr = norm_path(spec.stderr_path or f"~/{self._jobs_dir}/{spec.name}.e")
        lines.append(f"#$ -o {stdout}")
        lines.append(f"#$ -e {stderr}")

        lines.append(f"#$ -l h_rt={hms}")

        gpus = res.gpus if res.gpus else (res.gpu_cores_per_process or 0)
        if gpus:
            lines.append(f"#$ -l gpu={gpus}")

        lines.append(f"#$ -pe {pe} {slots}")

        return "\n".join(lines) + "\n"

    def _gpu_prologue(self, spec: JobSpec) -> str:
        """GPU CVD export block (empty string when no GPUs requested).

        GE's RSMAP exposes the allocated device index via $SGE_HGR_gpu
        (space-separated for multiple GPUs); translated here to
        CUDA_VISIBLE_DEVICES (comma-separated) so CUDA runtimes see only the
        assigned device(s). Guarded for the CPU-job case (unset variable).
        """
        res = spec.resources
        gpus = res.gpus if res.gpus else (res.gpu_cores_per_process or 0)
        if not gpus:
            return ""
        return (
            '# GE GPU isolation: translate SGE_HGR_gpu index -> CUDA_VISIBLE_DEVICES\n'
            'if [ -n "$SGE_HGR_gpu" ]; then\n'
            '    export CUDA_VISIBLE_DEVICES="$(echo "$SGE_HGR_gpu" | tr \' \' \',\')"\n'
            'fi\n'
        )

    def render_script(self, spec: JobSpec) -> str:
        """Render spec as a complete GE batch script: #$ directives, GPU CVD
        export block (only when GPUs > 0), then the scheduler-neutral body."""
        res = spec.resources
        gpu_requested = bool(res.gpus or res.gpu_cores_per_process)

        header = self._header(spec)
        prologue = self._gpu_prologue(spec)
        body = render_body(spec, gpu_requested=gpu_requested, gpu_vendor_flag="--nv")

        if prologue:
            return header + prologue + body
        return header + body

    def submit(self, spec: JobSpec) -> dict:
        """Write a batch script and submit it with qsub -terse."""
        script_content = self.render_script(spec)
        remote_path = write_remote_file(self.facility, f"{self._jobs_dir}/{spec.name}.sh", script_content)

        qsub = self._qbin("qsub")
        quoted = shlex.quote(remote_path)
        output = run_command(self.facility, f"chmod +x {quoted} && {qsub} -terse {quoted}")
        job_id = output.strip().splitlines()[-1].strip() if output.strip() else ""
        if not job_id.isdigit():
            raise RuntimeError(f"qsub did not return a numeric job id; got: {output!r}")
        return {"job_id": job_id, "script_path": remote_path}

    def _job_from_qstat(self, fields: dict[str, str]) -> Job:
        jid = fields.get("JB_job_number", "")
        state_letter = fields.get("state", "")
        state = map_ge_state(state_letter)
        start_raw = fields.get("JAT_start_time", "") or fields.get("JB_submission_time", "")
        epoch = to_epoch(start_raw)
        return Job(
            id=jid,
            status=JobStatus(
                state=state,
                time=epoch,
                message=fields.get("queue_name") or state_letter or None,
                meta_data={
                    "scheduler": "gridengine",
                    "native_state": state_letter,
                    "queue": fields.get("queue_name", ""),
                    "slots": fields.get("slots", ""),
                    "name": fields.get("JB_name", ""),
                },
            ),
        )

    def _job_from_qacct(self, record: dict[str, str]) -> Job:
        """failed!=0 -> FAILED; exit_status!=0 -> FAILED; else COMPLETED."""
        jid = record.get("jobnumber", "")
        failed = record.get("failed", "0").split()[0]  # e.g. "0" or "1  (Interrupted)"
        try:
            exit_code = int(record.get("exit_status", "0"))
        except ValueError:
            exit_code = None

        if failed != "0":
            state = JobState.FAILED
        elif exit_code is not None and exit_code != 0:
            state = JobState.FAILED
        else:
            state = JobState.COMPLETED

        epoch = to_epoch(record.get("end_time", ""))
        return Job(
            id=jid,
            status=JobStatus(
                state=state,
                time=epoch,
                exit_code=exit_code,
                message=record.get("failed") if failed != "0" else None,
                meta_data={
                    "scheduler": "gridengine",
                    "native_state": "qacct",
                    "queue": record.get("qname", ""),
                    "hostname": record.get("hostname", ""),
                    "slots": record.get("slots", ""),
                    "name": record.get("jobname", ""),
                    "failed": record.get("failed", ""),
                    "wallclock": record.get("wallclock", ""),
                },
            ),
        )

    @staticmethod
    def _parse_qstat_xml(xml_text: str) -> list[dict[str, str]]:
        """Parse `qstat -xml` output into a list of field dicts.

        Uses a simple regex rather than pulling in xml.etree to keep the
        dependency footprint minimal. Only top-level job_list entries are
        extracted (running + pending; not array-task sub-rows).
        """
        rows: list[dict[str, str]] = []
        for job_block in re.finditer(r"<job_list[^>]*>(.*?)</job_list>", xml_text, re.DOTALL):
            block = job_block.group(1)
            fields: dict[str, str] = {}
            state_attr = re.search(r'<job_list[^>]*state="([^"]*)"', job_block.group(0))
            if state_attr:
                fields["_list_state"] = state_attr.group(1)
            for tag_m in re.finditer(r"<([A-Za-z_]+)>([^<]*)</\1>", block):
                fields[tag_m.group(1)] = tag_m.group(2).strip()
            rows.append(fields)
        return rows

    @staticmethod
    def _parse_qacct_records(text: str) -> list[dict[str, str]]:
        """Parse `qacct -j <id>` (or `qacct -o USER -d N`) output. qacct
        separates records with a line of `=` characters."""
        records: list[dict[str, str]] = []
        current: dict[str, str] = {}
        for line in text.splitlines():
            if re.match(r"^=+$", line.strip()):
                if current:
                    records.append(current)
                    current = {}
                continue
            m = re.match(r"^(\S+)\s+(.*)", line)
            if m:
                current[m.group(1)] = m.group(2).strip()
        if current:
            records.append(current)
        return records

    def get_statuses(self, job_ids: list[str]) -> list[Job]:
        """1. qstat -xml for live jobs. 2. qacct -j <id> for anything not
        found live (qacct may lag briefly after a job finishes; qstat is
        authoritative for just-finished jobs still appearing there)."""
        if not job_ids:
            return []

        qstat = self._qbin("qstat")
        live_jobs: dict[str, Job] = {}
        try:
            xml_out = run_command(self.facility, f"{qstat} -xml")
            for row in self._parse_qstat_xml(xml_out):
                jid = row.get("JB_job_number", "")
                if jid:
                    live_jobs[jid] = self._job_from_qstat(row)
        except RuntimeError:
            pass  # qstat may fail if no jobs are running; continue to qacct

        result: list[Job] = []
        missing_ids: list[str] = []
        for jid in job_ids:
            if jid in live_jobs:
                result.append(live_jobs[jid])
            else:
                missing_ids.append(jid)

        qacct = self._qbin("qacct")
        for jid in missing_ids:
            try:
                acct_out = run_command(self.facility, f"{qacct} -j {shlex.quote(jid)}")
                records = self._parse_qacct_records(acct_out)
                if records:
                    result.append(self._job_from_qacct(records[-1]))
                else:
                    result.append(Job(id=jid, status=JobStatus(state=JobState.UNKNOWN, meta_data={"scheduler": "gridengine"})))
            except RuntimeError as exc:
                result.append(Job(id=jid, status=JobStatus(state=JobState.UNKNOWN, message=str(exc), meta_data={"scheduler": "gridengine"})))

        return result

    def get_recent_statuses(self, since: str = "now-2days") -> list[Job]:
        """Merge live jobs (qstat -u $USER -xml) with recent history
        (qacct -o $USER -d <days>, parsed from `since`'s day count when it
        looks like "now-Ndays", else 2). qstat wins for IDs in both (handles
        qacct flush lag)."""
        days = 2
        m = re.match(r"now-(\d+)days?$", since)
        if m:
            days = int(m.group(1))

        qstat = self._qbin("qstat")
        qacct = self._qbin("qacct")

        live: dict[str, Job] = {}
        try:
            xml_out = run_command(self.facility, f"{qstat} -u $USER -xml")
            for row in self._parse_qstat_xml(xml_out):
                jid = row.get("JB_job_number", "")
                if jid:
                    live[jid] = self._job_from_qstat(row)
        except RuntimeError:
            pass

        historical: dict[str, Job] = {}
        try:
            acct_out = run_command(self.facility, f"{qacct} -o $USER -d {days}")
            for rec in self._parse_qacct_records(acct_out):
                jid = rec.get("jobnumber", "")
                if jid and jid not in live:
                    historical[jid] = self._job_from_qacct(rec)
        except RuntimeError:
            pass

        merged = {**historical, **live}
        return list(merged.values())

    def cancel(self, job_id: str) -> Job | str:
        """qdel, then report the resulting state (CANCELED on success;
        UNKNOWN + message if qdel fails, e.g. the job already finished)."""
        qdel = self._qbin("qdel")
        try:
            run_command(self.facility, f"{qdel} {shlex.quote(job_id)}")
        except RuntimeError as exc:
            return Job(id=job_id, status=JobStatus(state=JobState.UNKNOWN, message=str(exc), meta_data={"scheduler": "gridengine"}))
        return Job(id=job_id, status=JobStatus(state=JobState.CANCELED, message=f"qdel {job_id} succeeded", meta_data={"scheduler": "gridengine"}))
