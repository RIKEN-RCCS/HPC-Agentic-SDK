---
name: hecbench-kernel-matching
description: Identify which HeCBench benchmarks are most similar to the important kernels in a user's code. Use for comparable benchmarks, proxy workloads, or kernel analogues in HPC and accelerated code.
---

# HeCBench Kernel Matching

Use this skill when the user wants a workload match, not merely a benchmark name lookup. The catalog below is intended to support a first-pass match without opening HeCBench source code.

## What HeCBench Contains

HeCBench is a heterogeneous benchmark suite of roughly 540 named workloads. Some entries are application kernels, some are mini-applications, and some are deliberately small language, runtime, library, or hardware-feature tests.

The README groups benchmarks into these useful families:

| Family | Kernel motifs represented | Examples |
|---|---|---|
| Bandwidth and communication | copy, triad, vector add, peer-to-peer, collectives, latency, cache/storage movement | `babelstream`, `triad`, `vadd`, `memcpy`, `allreduce`, `p2p` |
| Dense linear algebra | GEMM, GEMV, dot products, factorizations, transforms, small-matrix batches | `blas-gemm`, `blas-gemmBatched`, `gemv`, `blas-dot`, `lud`, `ludb` |
| Sparse and graph computation | SpMV/SpMM, sparse formats, triangular solve, graph traversal, centrality, shortest paths | `spmv`, `spmm`, `spgemm`, `sptrsv`, `bfs`, `sssp`, `page-rank` |
| Stencils and PDE/simulation | nearest-neighbor grids, structured updates, finite differences, lattice methods, particle interactions, reductions over physical state | `stencil1d`, `stencil3d`, `heat2d`, `laplace3d`, `fdtd3d`, `d2q9_bgk`, `nbody` |
| ML and tensor kernels | GEMM-like layers, convolutions, normalization, activations, attention, scans, sampling, embedding and scatter/gather | `attentionMultiHead`, `softmax-fused`, `layernorm`, `dwconv`, `unfold`, `sampling`, `ge-spmm` |
| Image and signal processing | convolution/filter windows, transforms, interpolation, correlation, reconstruction, regular-grid image updates | `convolution3D`, `bm3d`, `dct8x8`, `mriQ`, `sad`, `fft`, `sosfil` |
| Reductions and data movement | reduction, scan, histogram, compaction, segmented operations, gather/scatter, atomics | `scan`, `segment-reduce`, `histogram`, `sc`, `scatterAdd`, `atomicReduction` |
| Sorting and selection | radix/bitonic/merge/hybrid sort, key-value sort, top-k, partition/split | `radixsort`, `bitonic-sort`, `hybridsort`, `sortKV`, `topk` |
| Irregular/search/sequence work | string search, sequence alignment, suffix arrays, tree/graph search, hashing and lookup | `grep`, `bfs`, `nw`, `sa`, `wordcount`, `jenkins-hash` |
| Monte Carlo and numerical sampling | random/quasi-random generation, independent trials, stochastic updates, pricing and integration | `sobol`, `mt`, `rng-wallace`, `black-scholes`, `vmc`, `gibbs` |
| Domain workloads | bioinformatics, geoscience, finance, robotics, cryptography, and multiphysics applications | `minimap2`, `aidw`, `haversine`, `inversek2j`, `aes`, `miniWeather` |
| Feature and microbenchmarks | launch overhead, streams, atomics, synchronization, warp/subgroup operations, memory layout, precision/intrinsics | `kernelLaunch`, `concurrentKernels`, `streamCreateCopyDestroy`, `shuffle`, `pointerchase`, `wmma` |

These families describe what a benchmark does, not necessarily how its hottest kernel behaves. A domain label such as “simulation” can contain a stencil, sparse solve, particle method, reduction, or irregular traversal. Conversely, a benchmark in “machine learning” may be a generic GEMM, normalization, scan, or data-layout kernel.

## Motif Catalog

Use this catalog to narrow candidates from a kernel description. Names in one row are alternatives with the same dominant motif; the benchmark’s domain is secondary.

| Motif | HeCBench candidates |
|---|---|
| Streaming elementwise / bandwidth | `babelstream`, `cmembench`, `memcpy`, `memtest`, `threadcpy`, `triad`, `vadd`, `reshapeKVCache`, `storeKVCache`, `reverse`, `reverse2D`, `pad`, `conversion`, `adjacent`, `pointwise`, `relu`, `silu`, `gelu`, `flip` |
| Dense matrix/vector algebra | `blas-gemm`, `blas-gemmBatched`, `blas-gemmStridedBatched`, `blas-gemmEx`, `blas-gemmEx2`, `blas-groupgemm`, `blas-fp4gemm`, `blas-fp8gemm`, `blas-mxfp6gemm`, `blas-mxfp8gemm`, `gemv`, `blas-dot`, `axpby`, `geam`, `hadamard`, `matrixT`, `matrix-rotate`, `lut-gemm`, `quant3MatMul`, `f16sp`, `f8cast` |
| Sparse matrix algebra | `spmv`, `simpleSpmv`, `spmm`, `spgemm`, `sddmm-batch`, `spgeam`, `ge-spmm` |
| Sparse formats / sparse preprocessing | `spd2s`, `sps2d`, `spsort`, `spnnz`, `sptrsv`, `spaxpby`, `spgeam`, `ge-spmm`, `simpleSpmv` |
| Reduction / statistics | `atomicReduction`, `atomicAggregate`, `fma`, `filter`, `minmax`, `stddev`, `norm2`, `kurtosis`, `rowwiseMoments`, `channelSum`, `histogram`, `segment-reduce`, `bincount`, `nonzero` |
| Prefix scan / compaction / partition | `scan`, `scan2`, `scan3`, `bscan`, `sc`, `contract`, `split`, `scatter`, `scatterAdd`, `scatterThrust`, `adjacent`, `nonzero`, `filter` |
| Atomics and contention | `atomicCAS`, `atomicCost`, `atomicIntrinsics`, `atomicPerf`, `atomicSystemWide`, `atomicAggregate`, `atomicReduction`, `scatterAdd`, `histogram` |
| Regular-grid stencil / finite difference | `stencil1d`, `stencil3d`, `heat`, `heat2d`, `hotspot`, `hotspot3D`, `laplace`, `laplace3d`, `jacobi`, `fdtd3d`, `iso2dfd`, `sw4ck`, `rtm8`, `hypterm`, `adv`, `easyWave`, `pathfinder` |
| Lattice / local-neighborhood physics | `d2q9_bgk`, `d3q19_bgk`, `fluidSim`, `lid-driven-cavity`, `rayleighBenardConvection`, `reaction`, `miniWeather`, `s3d`, `cobahh`, `vanGenuchten`, `wsm5` |
| Dense convolution / local windows | `convolution1D`, `convolution3D`, `convolutionSeparable`, `convolutionDeformable`, `dwconv`, `dwconv1d`, `winograd`, `boxfilter`, `bilateral`, `medianfilter`, `recursiveGaussian`, `sobel`, `morphology`, `maxpool3d`, `pool` |
| FFT / transform / spectral | `fft`, `dct8x8`, `fwt`, `hwt1d`, `ntt`, `zmddft`, `lombscargle`, `slit`, `sosfil`, `hadamard`, `matrixT` |
| Tensor normalization / activation / fused pointwise | `layernorm`, `rmsnorm`, `groupnorm`, `rowwiseMoments`, `softmax`, `softmax-fused`, `softmax-online`, `addBiasResidualLayerNorm`, `addBiasQKV`, `crossEntropy`, `scel`, `gelu`, `geglu`, `glu`, `silu`, `relu`, `dropout` |
| Attention / sequence tensor movement | `attention`, `attentionMultiHead`, `attentionMultiHeadKVCache`, `attention-paged`, `attentionMergeState`, `qkv`, `reshapeKVCache`, `storeKVCache`, `rotary`, `unfold`, `vol2col`, `permute`, `mergeVS` |
| Gather / scatter / irregular indexing | `scatter`, `scatterAdd`, `scatterThrust`, `remap`, `permute`, `nonzero`, `bincount`, `dense-embedding`, `mask`, `overlay`, `p4`, `sampling` |
| Sorting / selection / ranking | `bitonic-sort`, `radixsort`, `radixsort2`, `quicksort`, `merge`, `hybridsort`, `sort`, `sortKV`, `segsort`, `warpsort`, `topk`, `split`, `moe-align` |
| Graph traversal / sparse irregular graph | `bfs`, `sssp`, `page-rank`, `cc`, `gc`, `hbc`, `mis`, `floydwarshall`, `floydwarshall2`, `rsmt`, `hungarian`, `b+tree`, `ge-spmm` |
| Particle / pairwise / all-to-all interaction | `nbody`, `bh`, `all-pairs-distance`, `knn`, `minkowski`, `braycurtis`, `hellinger`, `jaccard`, `haversine`, `hausdorff`, `particlefilter`, `particles`, `particle-diffusion`, `lavaMD`, `sph`, `aidw` |
| Monte Carlo / random generation | `mt`, `mrg32k3a`, `qrg`, `rng-wallace`, `sobol`, `urng`, `gibbs`, `metropolis`, `vmc`, `pso`, `black-scholes`, `binomial`, `aop`, `feynman-kac` |
| Search / matching / dynamic programming | `grep`, `bsearch`, `keogh`, `ss`, `sss`, `tsp`, `nw`, `fsm`, `local-ht`, `match`, `sad`, `seam-carving`, `pathfinder`, `dp`, `floydwarshall` |
| Sequence / bioinformatics alignment | `bsw`, `ccs`, `cm`, `diamond`, `extend2`, `frna`, `ga`, `logan`, `minimap2`, `nbnxm`, `nw`, `pcc`, `prna`, `sa`, `snake`, `epistasis` |
| Hashing / encoding / cryptography | `aes`, `bitcracker`, `chacha20`, `crc64`, `jenkins-hash`, `keccaktreehash`, `md5hash`, `merkle`, `murmurhash3`, `present`, `base64e`, `ans`, `entropy`, `ldpc`, `rle`, `lzss`, `bitpacking` |
| Small dense solves / factorizations | `lud`, `ludb`, `slu`, `gels`, `eigenvalue`, `determinant`, `jacobian`, `jacobi`, `thomas`, `tridiagonal`, `lanczos`, `rsc`, `rfs` |
| Communication / multi-stage synchronization | `allreduce`, `ccl`, `pingpong`, `ring`, `p2p`, `simpleMultiDevice`, `overlap`, `concurrentKernels`, `graphExecution`, `awbarrier`, `threadfence`, `nosync` |
| Launch / memory / execution microbenchmarks | `kernelLaunch`, `streamCreateCopyDestroy`, `streamOrderedAllocation`, `streamPriority`, `streamUM`, `mallocFree`, `pointerchase`, `prefetch`, `zerocopy`, `pitch`, `layout`, `interleave`, `mixbench`, `maxFlops`, `ert` |

The catalog is motif-oriented and intentionally allows overlap. For example, `ge-spmm` belongs to sparse matrix algebra and graph/ML workloads, while `histogram` belongs to both reduction and atomic-contention motifs. Preserve these multiple interpretations when ranking.

## Kernel Fingerprints

Translate the user's description into these fields before selecting benchmarks. The fields are more informative than the application's scientific name.

| Fingerprint | Questions to answer |
|---|---|
| Work unit | Is one output produced per element, row, tile, particle, edge, sequence, or independent trial? |
| Dependencies | Are outputs independent, a reduction, a prefix dependency, an iteration, a recurrence, or a graph traversal? |
| Access | Are accesses contiguous, strided, tiled, transposed, indirect, neighbor-based, or random? Is the operation gather, scatter, or both? |
| Reuse | Does data stay in a local window, shared tile, row, cache line, or register, or is it streamed once? |
| Arithmetic | Is it low-order arithmetic, transcendental-heavy, complex-valued, matrix-heavy, bitwise, or atomics-heavy? |
| Irregularity | Do rows, particles, paths, graph degrees, sequence lengths, or branches vary substantially? |
| Synchronization | Is there a barrier per tile, a global reduction, atomics to shared outputs, an iterative convergence loop, or inter-stage communication? |
| Shape | Is the data a 1D/2D/3D grid, dense matrix, sparse matrix, tensor, image, graph, sequence, or particle list? |

Use the following distinctions when the user's wording is broad:

- “Elementwise” means `vadd`, `pointwise`, `conversion`, `relu`, or similar streaming work; it does not imply `blas-gemm`.
- “Matrix multiplication” means GEMM candidates. “Matrix-vector,” “dot,” “outer product,” “contraction,” and “small independent matrices” should be separated into `gemv`, `blas-dot`, `sddmm-batch`, or `ludb`-like candidates.
- “Sparse” is incomplete. Choose among CSR-like SpMV, sparse matrix-matrix work, sparse triangular solve, sparse format conversion, graph traversal, and sparse tensor/message-passing behavior.
- “Stencil” means repeated neighbor reads on a regular grid. If the neighborhood is an image window, consider the filtering/convolution group; if particles choose neighbors dynamically, consider the particle/pairwise group.
- “Reduction” should be split into one-output reductions, row/segment reductions, histograms, scans, atomics, or compaction.
- “Monte Carlo” can mean random-number generation, independent path/trial evaluation, Markov-chain state updates, or numerical integration; match the inner loop, not the label.
- “FFT-like” includes Fourier transforms, but not every spectral method is an FFT. `fft`, `dct8x8`, `fwt`, `hwt1d`, `ntt`, and `zmddft` represent different transform shapes.
- “Attention” usually combines matrix products, reductions, softmax, masking, and irregular KV-cache movement. Rank the fused attention benchmark only when those stages are fused in the user's kernel.

## Detailed Matching Rules

### Streaming, bandwidth, and layout

Use `babelstream` for a family of copy/scale/add/triad streaming kernels; `triad` and `vadd` for simple read-read-write arithmetic; `memcpy` for pure copies; `threadcpy` for thread-driven copy behavior; and `cmembench`/`memtest` for lower-level bandwidth or memory behavior. Use `reshapeKVCache`, `storeKVCache`, `reverse`, `pad`, `conversion`, `adjacent`, `flip`, and `pointwise` when indexing/layout or a simple transformation is part of the work. These are good proxies for bandwidth pressure and coalescing, but poor proxies for compute-heavy kernels with substantial reuse.

### Dense algebra and factorizations

Use GEMM candidates when each output accumulates many products over a shared dimension and tiles can be reused. Use `blas-gemmBatched` or `blas-gemmStridedBatched` when there are many small matrices rather than one large matrix. Use `blas-gemmEx`, `blas-gemmEx2`, `blas-fp4gemm`, `blas-fp8gemm`, `blas-mxfp6gemm`, and `blas-mxfp8gemm` when low-precision or mixed-format scaling is part of the motif. Use `gemv` when each output is a row dot product with little reuse across rows, and `blas-dot` for a single reduction over paired vectors. Use `axpby` for linear combinations of vectors, `geam` for matrix addition, and `hadamard` for elementwise products. Use `lud` for blocked/general LU-style work and `ludb` for many small independent factorizations; use `gels`, `eigenvalue`, `determinant`, `jacobi`, `lanczos`, `thomas`, and `tridiagonal` when the solve or eigensolver structure is the distinguishing feature.

### Sparse and irregular linear algebra

Use `spmv` or `simpleSpmv` for a sparse matrix times dense vector with indirect column reads and row-wise reductions. Use `spmm`/`spgemm` when both operands or the output have sparse structure and the work includes products and sparse accumulation. Use `sddmm-batch` for dense products evaluated only at sparse locations. Use `sptrsv` for dependency-constrained sparse triangular solves, not ordinary SpMV. Use `spd2s`, `sps2d`, `spnnz`, and `spsort` for format conversion, nonzero counting, and sparse indexing rather than numerical kernels. Use `spgeam` for sparse matrix addition/merge and `spaxpby` for sparse linear combinations. Use `ge-spmm` when sparse multiplication is organized around graph/neural-message-passing behavior.

### Stencils, filters, and local neighborhoods

Use `stencil1d` or `stencil3d` for explicit fixed-radius neighbor updates. Use `heat2d`, `laplace`, `laplace3d`, `jacobi`, `hotspot`, `hotspot3D`, `fdtd3d`, `iso2dfd`, `sw4ck`, and `rtm8` for repeated finite-difference or wave/thermal updates. Use `d2q9_bgk` and `d3q19_bgk` for lattice-Boltzmann-style local state transitions. Use `convolution1D`, `convolution3D`, `convolutionSeparable`, `dwconv`, and `dwconv1d` when a weighted window is applied; use `convolutionDeformable` when offsets make the window irregular. Use `boxfilter`, `bilateral`, `medianfilter`, `recursiveGaussian`, `sobel`, and `morphology` for image-window operations with their characteristic min/max, gradient, or recursive behavior. Use `winograd` when the convolution is transformed into small matrix/tile operations.

### Reductions, scans, histograms, and compaction

Use `scan`, `scan2`, and `scan3` for prefix sums; distinguish `scan`-style algorithmic kernels from `scan3`-style library-oriented scans when implementation detail matters. Use `segment-reduce` for independent reductions over variable-length segments and `atomicReduction` for atomics-based accumulation. Use `minmax`, `norm2`, `stddev`, `kurtosis`, `rowwiseMoments`, and `channelSum` for reduction shape and statistic. Use `histogram` or `bincount` when many inputs update a small set of bins. Use `sc` for stream compaction and `filter`/`nonzero` when a predicate produces a packed output. Use `contract`, `scatter`, `scatterAdd`, and `scatterThrust` when index production or indexed writes dominate. Use the atomic benchmarks when contention, memory scope, or compare-and-swap behavior is itself the target.

### Tensor and ML-style kernels

Use `layernorm`, `rmsnorm`, `groupnorm`, and `rowwiseMoments` for statistics over a row, feature vector, group, or channel. Use `softmax`, `softmax-fused`, and `softmax-online` for exponentiation plus reduction; choose fused variants only when masking/scaling or online streaming is central. Use `addBiasQKV`, `addBiasResidualLayerNorm`, `qkv`, and `rotary` for small fused tensor transforms surrounding attention. Use `attentionMultiHead` for conventional multi-head attention, `attentionMultiHeadKVCache` or `attention-paged` for cache-oriented irregular reads, and `attentionMergeState` for combining partial attention states. Use `unfold` and `vol2col` when tensor neighborhoods are materialized before a later matrix operation. Use `dense-embedding`, `permute`, `remap`, `mergeVS`, `mask`, and `sampling` for data movement, indexing, or selection rather than arithmetic-heavy neural layers. Use `moe`, `moe-align`, and `moe-sum` when routing, sorting by expert, or indexed accumulation is the key behavior.

### Graphs, particles, and irregular workloads

Use `bfs` for frontier-based traversal, `sssp` for repeated relaxation with irregular graph reads, `page-rank` for iterative sparse gather/reduction, and `cc`, `gc`, `mis`, `hbc`, `floydwarshall`, and `hungarian` for their corresponding graph algorithms. Use `nbody`, `bh`, `lavaMD`, `sph`, `particles`, and `particle-diffusion` for particle interactions; distinguish all-pairs work from tree-pruned (`bh`) or neighbor/local interaction. Use `all-pairs-distance`, `knn`, `minkowski`, `braycurtis`, `hellinger`, `jaccard`, `haversine`, and `hausdorff` for pairwise distance motifs, with the distance metric and data reuse as secondary features. Use `aidw` when interpolation combines neighbor search with weighted accumulation.

### Sorting, search, sequences, and encoding

Use `radixsort`, `bitonic-sort`, `quicksort`, `merge`, `hybridsort`, `sort`, `sortKV`, `segsort`, and `warpsort` according to key/value structure, segmentation, and sorting strategy. Use `topk` when only the largest K values are needed, and `split` when partitioning is the important phase. Use `grep`, `bsearch`, `ss`, `keogh`, and `match` for search or matching with irregular control flow. Use `nw`, `bsw`, `fsm`, `minimap2`, `sa`, `snake`, `frna`, `diamond`, and related sequence benchmarks for alignment, automata, suffix-array, or sequence-filtering motifs. Use `aes`, `chacha20`, `md5hash`, `jenkins-hash`, `murmurhash3`, `keccaktreehash`, and `merkle` for fixed-round or tree/hash computation; use `ans`, `base64e`, `crc64`, `entropy`, `ldpc`, `rle`, `lzss`, and `bitpacking` for encoding, compression, or verification dominated by bit operations and variable-length data.

### Randomness and numerical simulation

Use `mt`, `mrg32k3a`, `qrg`, `rng-wallace`, `sobol`, and `urng` when random-number generation is the kernel. Use `black-scholes`, `binomial`, `aop`, and `libor` for independent financial paths or option calculations. Use `gibbs`, `metropolis`, `vmc`, `pso`, `feynman-kac`, and `projectile` when random samples drive a longer trial or state-update loop. Use `ace`, `goulash`, `reaction`, `rushlarsen`, `s3d`, `miniWeather`, `lulesh`, `miniFE`, `simplemoc`, and related simulation names only after identifying whether their inner work is a stencil, sparse solve, particle update, recurrence, or reduction.

## Source-Derived Benchmark Cards

These cards capture distinctions found by inspecting representative implementation families. Prefer the card description over a broad README category when one applies.

| Benchmark | Actual dominant structure | Match it to |
|---|---|---|
| `stencil1d` | Fixed-radius 1D neighbor update; low-dimensional regular reuse. | 1D finite differences, line stencils, local smoothing. |
| `stencil3d` | 3D diffusion-style stencil with multiple neighbor fields and local tile staging/barriers. | 3D regular-grid PDE updates with shared-neighborhood reuse. |
| `heat2d` | Repeated 2D Laplacian/heat update with ping-pong input/output grids. | 2D Jacobi/heat diffusion, not general dense matrix work. |
| `fdtd3d` | Radius-parameterized 3D finite difference with coefficient array and tiled local reuse. | Higher-order regular-grid stencil with tunable radius. |
| `sw4ck` | Several curvilinear high-order seismic kernels over 3D fields and metric/coefficient arrays. | High-order variable-coefficient wave propagation; stronger arithmetic and field coupling than a basic stencil. |
| `rtm8` | Reverse-time migration style wavefield update and imaging operations. | Seismic wave propagation with multiple field updates and time stepping. |
| `d2q9_bgk` / `d3q19_bgk` | Lattice-Boltzmann collide/stream state update with fixed velocity populations and iterative timesteps. | Structured local physics with many per-cell state values and a fixed neighbor pattern. |
| `adv` | Hex-element advection/cubature with geometry and interpolation data; element-local but indirect/tensor-heavy. | Unstructured finite-element advection, not a simple grid stencil. |
| `amgmk` | CSR matrix storage plus relaxation; sparse matrix-vector-like row operations. | Sparse iterative solver smoothers and CSR relax kernels. |
| `miniFE` | Finite-element assembly and sparse linear algebra, including sparse matvec, vector operations, and dot products. | Mixed FEM assembly/SpMV/BLAS-1 solver loops. |
| `spmv` | CSR/COO sparse matrix-vector multiplication with row reductions and indirect vector reads. | Canonical sparse operator application. |
| `spmm` / `spgemm` | Sparse matrix products with irregular output construction/accumulation. | Sparse matrix-matrix work; expect more irregularity than SpMV. |
| `sptrsv` | Sparse triangular solve with dependency/order constraints. | Solves with row dependencies, not independent sparse rows. |
| `page-rank` | Iterative map and reduce phases over graph adjacency plus convergence/difference calculation. | Iterative graph gather/reduce with a global convergence step. |
| `bfs` | Frontier expansion with visited-state checks and irregular adjacency traversal. | Level-synchronous graph traversal and irregular atomics. |
| `sssp` | Repeated graph relaxation over variable-degree adjacency. | Irregular shortest-path relaxation, especially when work imbalance matters. |
| `floydwarshall` | Dense all-pairs dynamic-programming update over a cubic index space. | Regular dense DP, distinct from sparse graph traversal. |
| `all-pairs-distance` | Pairwise instance-distance kernels with per-pair reductions and multiple kernel variants. | Dense pairwise comparisons where each pair reads feature vectors. |
| `mriQ` | Complex-valued accumulation over coordinates and k-space-like samples; high arithmetic per output with irregular sample reuse. | Particle-to-grid / nonuniform transform / complex pairwise accumulation. |
| `degrid` | Nonuniform sample-to-image interpolation using coordinate lookup, grid correction, and compact convolution support. | Irregular gather/interpolation, especially radio-astronomy-style gridding. |
| `aidw` | Adaptive inverse-distance weighting with neighbor-distance/search-related work and a tiled variant. | Spatial interpolation with pairwise distances and local tiling. |
| `nbody` | Pairwise force calculation followed by velocity/position update; inverse-distance and square-root arithmetic. | All-pairs particle interaction with transcendental/reciprocal cost. |
| `bh` | Barnes-Hut tree-based force approximation. | Particle interactions with hierarchical pruning, not all-pairs uniform work. |
| `haccmk` | HACC particle-force microkernel using particle positions/masses and repeated distance arithmetic. | High-throughput particle force calculation with regular per-particle work. |
| `particlefilter` | Likelihood evaluation, weighted reduction, normalization, cumulative distribution, and resampling/index search. | Multi-stage stochastic filtering; only use as a whole-program proxy when several stages matter. |
| `kmeans` | Iterative point-to-centroid distance evaluation, membership selection, centroid accumulation, and RMSE. | Iterative clustering with pairwise distance plus reduction/assignment. |
| `gmm` | Gaussian-mixture expectation/maximization with likelihoods, covariance statistics, matrix inversion, and log/exp. | Dense statistical model fitting with reductions and transcendental functions. |
| `vmc` | Monte Carlo wavefunction/statistics evaluation, distance calculations, and block reductions. | Stochastic sampling plus local numeric evaluation and reduction. |
| `simplemoc` | Attenuation along independent geometric segments with indexed material/flux data and exponential evaluation. | Independent path/segment transport with indirect reads and transcendental arithmetic. |
| `rainflow` | Branch-heavy rainflow cycle counting with extrema, history arrays, variable-length state, and multiple passes. | Irregular stateful sequence processing; poor match for regular map kernels. |
| `fft` | Fixed-size 1D FFT/IFFT stages with local storage and barriers between butterfly stages. | Butterfly transforms with staged synchronization. |
| `sosfil` | Second-order IIR filtering with per-signal state/history and recursive dependence. | Signal filtering where each signal has sequential recurrence; not a freely parallel stencil. |
| `histogram` | Pixel/bin accumulation with both global and local/shared atomic implementations. | Many-to-few updates, contention, privatization, and histogram reduction. |
| `hybridsort` | Histogram/bucket count, prefix scan, bucket scatter/sort, and merge passes. | Full multi-stage integer sort pipelines, not just a comparison sort. |
| `radixsort` | Digit-based integer/key sorting with histogram/prefix/partition phases. | Fixed-width key sorting and scan-heavy reordering. |
| `sortKV` | Key-value sorting where values must follow key permutations. | Reordering coupled records, not scalar-only sorting. |
| `topk` | Per-row selection of largest K values rather than total ordering. | Bounded selection with row-local reductions/partitioning. |
| `tridiagonal` | Multiple small-system solvers: cyclic reduction, parallel cyclic reduction, and sweep variants. | Batched narrow-band solves; choose when dependency topology is the key motif. |
| `lud` | Blocked LU with separate diagonal, perimeter, and internal update kernels using tiles and barriers. | Blocked factorization with staged triangular updates. |
| `ludb` | LU factorization of many small independent matrices. | Batched small dense solves, not a single large blocked factorization. |
| `blas-gemm` | Tiled matrix multiplication; some variants also exercise vendor BLAS paths. | Dense high-reuse multiply-accumulate. |
| `blas-gemmBatched` | Many independent GEMMs, usually small or medium dimensions. | Batched dense contractions with independent matrix instances. |
| `gemv` | Matrix-vector product with a row-wise dot and lower reuse than GEMM. | Matrix-vector operators and low-arithmetic-intensity dense algebra. |
| `attentionMultiHead` | Query/key dot products, softmax-like max/sum reductions, and value accumulation across heads. | Fused attention only when these stages are coupled. |
| `attentionMultiHeadKVCache` / `attention-paged` | Attention with cache-oriented, page/block-indexed key/value reads. | Attention dominated by irregular cache movement and decode-time shapes. |
| `layernorm` / `rmsnorm` | Per-row statistics followed by normalization and scale; reduction plus fused elementwise work. | Row-wise normalization, not generic reductions. |
| `unfold` / `vol2col` | Materialization of sliding tensor windows into a rearranged representation. | Gather-heavy layout expansion preceding convolution/GEMM. |
| `ge-spmm` | Sparse graph-neural-network message passing / sparse matrix-matrix behavior. | Sparse aggregation over graph edges with feature vectors. |
| `word2vec` | Embedding/context operations with reductions and irregular index access. | Sparse embedding updates and sampled learning, not dense neural layers. |
| `xsbench` | Randomized cross-section lookup through material/nuclide grids with indirect memory access. | Latency-bound random lookup with little spatial locality. |
| `minimap2` | Tiled sequence chaining/alignment with dynamic programming, trackers, and irregular sequence data. | Bioinformatics sequence processing with variable control flow and data dependence. |
| `su3` | Complex small-matrix nearest-neighbor lattice operation over sites. | Fixed-size complex matrix algebra embedded in a regular lattice. |

The cards are deliberately specific about what makes each benchmark useful and what it should not be confused with. When no card applies, use the motif catalog plus the README description, then state the uncertainty rather than inventing source-level details.

## Ranking and Evidence

Score a candidate on separate axes instead of using one vague similarity judgment:

1. **Core operation (0–4):** same mathematical kernel or algorithmic primitive.
2. **Dependency topology (0–3):** same map, reduction, scan, recurrence, iteration, or graph dependency.
3. **Memory behavior (0–3):** same contiguous/strided/tiled/indirect/neighbor/random access and reuse.
4. **Work irregularity (0–2):** same branch divergence, variable-length work, degree imbalance, or state dependence.
5. **Data shape (0–2):** same grid, matrix, sparse matrix, tensor, particle, sequence, or sample layout.
6. **Secondary arithmetic (0–2):** similar transcendental, complex, bitwise, atomic, or low-precision character.

Report the score qualitatively as high, medium, or low confidence. A benchmark with the same application domain but a different dependency topology should rank below a domain-unrelated benchmark with the same kernel structure. A bandwidth benchmark should be presented as a machine-balance proxy, not as an algorithmic analogue. A benchmark with several stages should only be ranked highly when the user's workload contains the same stage composition; otherwise match the individual stage instead.

Match by computational motif rather than application name: use stencil/finite-difference candidates for local grid updates; dense BLAS candidates for matrix products and contractions; sparse/graph candidates for sparse operators; reduction/scan candidates for accumulation and normalization; FFT candidates for spectral work; and Monte Carlo/random-number candidates for sampling loops. Use domain benchmarks only when their actual source-level access and arithmetic patterns agree.

## Workflow

1. Identify the key kernels in the user's code. If the kernels are not already known, investigate the code in depth enough to identify the dominant computational regions before matching.

2. Build a short signature for each important kernel:

   - mathematical operation or algorithm
   - dense, sparse, irregular, or stencil access
   - reuse/locality and approximate arithmetic intensity
   - parallel pattern: map, reduction, scan, gather/scatter, sort, graph traversal, synchronization, or communication
   - data shape, dimensionality, and precision

3. Use the motif catalog and the README descriptions to form the initial shortlist. Consult the local HeCBench data only to confirm spelling, category, available benchmark variants, arguments, or test metadata:

   - `HeCBench/README.md` for category lists and reference descriptions
   - `HeCBench/benchmarks.yaml` for categories and test metadata
   - matching directories under `HeCBench/src/` only when a top candidate is ambiguous or the user asks for source-level confirmation

4. Rank candidates by kernel behavior: algorithmic structure; memory/access pattern; parallel decomposition and synchronization; and precision/data shape. Treat README categories as a search aid, not proof of similarity.

5. Return a concise ranked table. For each candidate include the benchmark name, matched kernel(s), why it is similar, an important mismatch or limitation, and the source path(s) used.

Give several candidates when different kernels map to different benchmark families. Say explicitly when a benchmark is only a proxy for one aspect, such as memory bandwidth or a reduction. Do not imply that semantic similarity guarantees comparable performance; recommend validating the shortlist on the target device and representative problem sizes.
