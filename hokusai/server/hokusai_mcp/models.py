"""Data models mirroring the IRI Facility API schemas.

The IRI (Integrated Research Infrastructure) Facility API is the DOE
standard for programmatic facility access (spec at api.alcf.anl.gov/openapi.json).
Its compute schemas follow PSI/J: a JobSpec with ResourceSpec + JobAttributes,
and a normalized JobState. We implement a pragmatic subset; deviations are
noted in IRI_CHECKLIST.md at the repository root.

HOKUSAI BigWaterfall2 (HBW2) is a CPU-first system: the bulk of it is the
Massively Parallel Computer (MPC) and the Large Memory server (LMC), addressed
through cores / processes / threads. A small 4-node GPU server exists for
postprocessing; GPUs are an optional, rarely-used resource here.
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
    "REJECTED": JobState.FAILED,
}


def map_slurm_state(native: str) -> JobState:
    # sacct reports e.g. "CANCELLED by 12345"
    return _SLURM_STATE_MAP.get(native.split()[0].rstrip("+"), JobState.UNKNOWN)


class ResourceSpec(BaseModel):
    """Resources for a job (PSI/J ResourceSpec + HBW2 extensions).

    HBW2 jobs are described primarily in CPU terms: node_count,
    processes_per_node (MPI ranks), and cpu_cores_per_process (threads per
    rank, e.g. OpenMP). memory is per-node in bytes (maps to --mem).

    GPUs are optional and only relevant on the small GPU server (partition
    `gpu`/`gpu_i`): set `gpus` (the total number of GPUs, maps to --gpus).
    gpu_cores_per_process is the PSI/J standard equivalent; if both are set,
    `gpus` takes precedence.
    """
    node_count: int = 1
    process_count: int | None = Field(None, description="Total MPI processes (alternative to processes_per_node × node_count)")
    processes_per_node: int = 1
    cpu_cores_per_process: int | None = Field(None, description="Cores per process — OpenMP threads (maps to --cpus-per-task)")
    gpu_cores_per_process: int | None = Field(None, description="PSI/J standard GPU field; prefer `gpus` on HBW2")
    gpus: int | None = Field(None, description="HBW2 extension: total GPUs for the job (maps to --gpus). GPU server only.")
    exclusive_node_use: bool = Field(False, description="Request exclusive node allocation (--exclusive)")
    memory: int | None = Field(None, description="Memory per node in bytes (maps to --mem)")


class JobAttributes(BaseModel):
    """Scheduler attributes (IRI/PSI/J JobAttributes subset)."""
    duration: int | str = Field(
        3600,
        description="Wall time as integer seconds or HH:MM:SS / D-HH:MM:SS string (HBW2 default 1h)",
    )
    queue_name: str = Field("mpc", description="Slurm partition (mpc, mpc_l, lmc, gpu, gpu_i)")
    account: str | None = Field(None, description="Slurm project ID to charge (e.g. RB999999); required by HBW2 — falls back to the config default")
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
    """Container specification (IRI Container); executed via singularity exec on HBW2.

    image must be a path to a .sif file (absolute or using $HOME), or a URI
    such as docker://ubuntu:24.04. GPU passthrough (--nv) is added automatically
    when the job requests GPUs (GPU server jobs only). launcher (e.g. 'srun') is
    placed outside singularity exec so MPI works.
    """
    image: str = Field(description="Singularity image path or URI (e.g. docker://ubuntu:24.04)")
    volume_mounts: list[VolumeMount] = Field(default_factory=list)


class JobSpec(BaseModel):
    """Job specification (IRI/PSI/J JobSpec subset).

    executable plus arguments form the command run inside the batch script;
    executable may be a shell line (e.g. 'module load intel && srun ./a.out').
    launcher, if set, is prepended to executable (e.g. 'srun').
    pre_launch / post_launch are script lines inserted before / after.
    If container is set, the command is wrapped in 'singularity exec'.
    """
    name: str = "hokusai-job"
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
