"""Data models mirroring the IRI Facility API schemas.

The IRI (Integrated Research Infrastructure) Facility API is the DOE
standard for programmatic facility access (spec at api.alcf.anl.gov/openapi.json).
Its compute schemas follow PSI/J: a JobSpec with ResourceSpec + JobAttributes,
and a normalized JobState. We implement a pragmatic subset; deviations are
noted in IRI_CHECKLIST.md at the repository root.
"""
from enum import Enum

from pydantic import BaseModel, Field


class JobState(str, Enum):
    """Normalized job states (IRI/PSI-J), mapped from Slurm native states."""
    NEW = "new"
    QUEUED = "queued"
    HELD = "held"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    UNKNOWN = "unknown"


_SLURM_STATE_MAP = {
    "PENDING": JobState.QUEUED,
    "CONFIGURING": JobState.QUEUED,
    "REQUEUED": JobState.QUEUED,
    "SUSPENDED": JobState.HELD,
    "RUNNING": JobState.ACTIVE,
    "COMPLETING": JobState.ACTIVE,
    "STAGE_OUT": JobState.ACTIVE,
    "COMPLETED": JobState.COMPLETED,
    "CANCELLED": JobState.CANCELED,
    "FAILED": JobState.FAILED,
    "TIMEOUT": JobState.FAILED,
    "OUT_OF_MEMORY": JobState.FAILED,
    "NODE_FAIL": JobState.FAILED,
    "BOOT_FAIL": JobState.FAILED,
    "DEADLINE": JobState.FAILED,
    "PREEMPTED": JobState.FAILED,
}


def map_slurm_state(native: str) -> JobState:
    # sacct reports e.g. "CANCELLED by 12345"
    return _SLURM_STATE_MAP.get(native.split()[0].rstrip("+"), JobState.UNKNOWN)


class ResourceSpec(BaseModel):
    """Resources for a job (PSI/J ResourceSpec + R-CCS Cloud extensions).

    On the R-CCS Cloud the partition selects the hardware family.
    gpus is an R-CCS Cloud extension that maps to --gpus=<n>; it is not
    needed for qc-gh200 or ng-dgx-m[0-3] (unified CPU+GPU superchips).
    gpu_cores_per_process is the PSI/J standard field and is accepted as
    a fallback when gpus is not set.
    """
    node_count: int = 1
    process_count: int | None = Field(None, description="Total processes (alternative to processes_per_node × node_count)")
    processes_per_node: int = 1
    cpu_cores_per_process: int | None = None
    gpu_cores_per_process: int | None = Field(None, description="PSI/J standard GPU field; prefer gpus on R-CCS Cloud")
    gpus: int | None = Field(None, description="R-CCS Cloud extension: maps to --gpus=<n>. Not needed for qc-gh200 or ng-dgx partitions.")
    exclusive_node_use: bool = Field(False, description="Request exclusive node allocation (--exclusive)")
    memory: int | None = Field(None, description="Memory per node in bytes (maps to --mem)")


class JobAttributes(BaseModel):
    """Scheduler attributes (IRI/PSI/J JobAttributes subset)."""
    duration: int | str = Field(
        3600,
        description="Wall time as integer seconds or HH:MM:SS / D-HH:MM:SS string",
    )
    queue_name: str = Field("genoa", description="Slurm partition — must match the hardware you intend to use")
    account: str | None = Field(None, description="Slurm account to charge (if required by site policy)")
    reservation_id: str | None = Field(None, description="Slurm reservation name (--reservation)")
    custom_attributes: dict[str, str] = Field(default_factory=dict)


class CompressionType(str, Enum):
    """Compression format for fs_compress / fs_extract (IRI CompressionType)."""
    NONE = "none"
    BZIP2 = "bzip2"
    GZIP = "gzip"
    XZ = "xz"


class VolumeMount(BaseModel):
    """A host path mounted into a container (IRI VolumeMount)."""
    source: str = Field(description="Host path to mount")
    target: str = Field(description="Path inside the container")
    read_only: bool = Field(True, description="Mount as read-only")


class Container(BaseModel):
    """Container specification (IRI Container); executed via singularity exec.

    image must be a path to a .sif file (absolute or using $HOME). GPU
    passthrough (--nv) is added automatically when the job requests GPUs.
    launcher (e.g. 'srun') is placed outside singularity exec so MPI works.
    """
    image: str = Field(description="Singularity image path or URI (e.g. docker://ubuntu:22.04)")
    volume_mounts: list[VolumeMount] = Field(default_factory=list)


class JobSpec(BaseModel):
    """Job specification (IRI/PSI/J JobSpec subset).

    executable plus arguments form the command run inside the batch script;
    executable may be a shell line (e.g. 'module load system/genoa mpi/openmpi-x86_64 && srun ./app').
    launcher, if set, is prepended to executable (e.g. 'srun').
    pre_launch / post_launch are script lines inserted before / after.
    If container is set, the command is wrapped in 'singularity exec'.

    Important: source /etc/profile is emitted automatically by render_script
    (required on R-CCS Cloud before any module commands). Do not add it manually.
    """
    name: str = "cloud-job"
    executable: str
    arguments: list[str] = Field(default_factory=list)
    directory: str | None = Field(None, description="Working directory for the job")
    environment: dict[str, str] = Field(default_factory=dict)
    inherit_environment: bool = Field(True, description="Inherit submission environment variables")
    stdin_path: str | None = Field(None, description="Path to use as stdin (--input)")
    stdout_path: str | None = None
    stderr_path: str | None = None
    resources: ResourceSpec = Field(default_factory=ResourceSpec)
    attributes: JobAttributes = Field(default_factory=JobAttributes)
    pre_launch: str | None = Field(None, description="Script lines to insert before executable")
    post_launch: str | None = Field(None, description="Script lines to insert after executable")
    launcher: str | None = Field(None, description="Launcher prefix, e.g. 'srun' or 'mpirun -np 4'")
    container: Container | None = Field(None, description="Run inside a Singularity container")


class JobStatus(BaseModel):
    """IRI-compliant job status (state + time + message + exit_code + meta_data).

    Slurm-specific detail (native_state, partition, nodes, workdir, elapsed,
    start/end times, queue reason) is carried in meta_data.
    """
    state: JobState
    time: float | None = Field(None, description="Epoch seconds: end_time if finished, start_time if running")
    message: str | None = Field(None, description="Human-readable status (queue reason, error, etc.)")
    exit_code: int | None = None
    meta_data: dict | None = Field(None, description="Slurm-specific fields: native_state, partition, nodes, workdir, elapsed, etc.")


class Job(BaseModel):
    """IRI Job: identifier + current status + originating spec."""
    id: str
    status: JobStatus | None = None
    job_spec: JobSpec | None = None
