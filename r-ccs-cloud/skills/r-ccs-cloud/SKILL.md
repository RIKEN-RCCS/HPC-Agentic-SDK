---
name: r-ccs-cloud
description: Reference information about the R-CCS cloud HPC systems — available machines, resources, modules, SLURM scripts, and login details. Use when the user is running jobs on R-CCS systems or needs to know how to connect, what hardware is available, or how to write a job script.
user-invocable: true
---

# R-CCS Cloud Systems

## Login

The url is login.cloud.r-ccs.riken.jp.

---

## Available Systems

| System   | Description                         | Nodes | Modules to Load                 |
|----------|-------------------------------------|-------|---------------------------------|
| fx700    | Fujitsu A64FX                       | 31    | system/fx700 FJSVstclanga       |
| genoa    | AMD EPYC 9684X                      | 16    | system/genoa mpi/openmpi-x86_64 |
| qc-gh200 | NVIDIA GH200 Grace Hopper Superchip | 8     | system/qc-gh200 nvhpc           |
| qc-a100	 | AMD EPYC 7713 x 2 + NVIDIA A100 x 8 | 2     | system/qc-a100 nvhpc            |

---

## Basic SLURM Script

Template job script, e.g.:

```bash
#!/bin/bash
#SBATCH --job-name=jobname # Job name
#SBATCH -p fx700 # Partition name
#SBATCH -N 1 # Number of nodes
#SBATCH -t 01:00:00 # Time

module load ...

srun ./myapp
```

## Notes

On the GPU nodes, options like:
```
#SBATCH --gres=gpu:1
```
Are not required. The exceptions are qc-a100, ai-l40s, and ai-h200-brc which require an option like:
```
#SBATCH --gpus=1
```
