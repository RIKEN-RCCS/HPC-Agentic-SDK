---
name: tadashi
description: Guide for using the Tadashi MCP server to check whether loop transformations are mathematically safe in C code. Use when analyzing loop dependencies, applying transformations like tiling or interchange, or verifying legality of polyhedral optimizations.
user-invocable: true
---

# Tadashi — Loop Transformation Safety Checker

Tadashi exposes two MCP tools for analyzing and transforming loops in C code with `#pragma scop` / `#pragma endscop` annotations marking the regions of interest.

---

## Tools

### `analyze_dependencies(c_code)`

Finds all SCOP regions in the given C source and reports their structure and legality.

**Returns:** For each SCOP — its index, number of schedule nodes, and whether it is currently legal.

**Use this first** before attempting any transformation to understand the loop structure.

### `transform_code(c_code, scop_idx, node_idx, transform, transform_args?)`

Applies a transformation to a specific node within a SCOP and returns the transformed C source, or explains why it is illegal.

**Parameters:**
- `c_code` — full C source with `#pragma scop` annotations
- `scop_idx` — index of the SCOP to transform (from `analyze_dependencies`)
- `node_idx` — index of the schedule node to transform
- `transform` — name of the transformation (see table below)
- `transform_args` — optional list of integers for parameterized transforms

**Supported transforms:**

| Transform | Args | Description |
|-----------|------|-------------|
| `INTERCHANGE` | — | Swap two loop levels |
| `TILE_2D` | `[tile_i, tile_j]` | Tile two innermost loops |
| `FUSE` | — | Fuse two loops |
| `DISTRIBUTE` | — | Distribute a loop |
| `SKEW` | — | Skew a loop |
| `UNROLL` | `[factor]` | Unroll by a given factor |

---

## Workflow

1. Call `analyze_dependencies` to identify SCOPs and their node counts.
2. Pick a SCOP and node index to target.
3. Call `transform_code` with the desired transform.
4. If legal, the transformed source is returned. If illegal, the reason is explained.

---

## Examples

**Check if loop interchange is safe:**
```
analyze_dependencies(<code>)         → SCOP 0: 5 nodes, legal=True
transform_code(<code>, 0, 1, "INTERCHANGE")
```

**Tile a stencil 32×32:**
```
transform_code(<code>, 0, 1, "TILE_2D", [32, 32])
```

**Illegal transform — what to expect:**
```
ILLEGAL: INTERCHANGE at SCOP 0 node 1 violates data dependencies.
```
The code is returned unchanged and the dependency violation is explained.
