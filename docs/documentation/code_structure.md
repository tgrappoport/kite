!!! Info

    This page is a developer-facing reference to KITE's C++ source layout and its compile-time
    configuration options. Users who are not modifying KITE itself should instead consult
    [Settings](settings.md) and [Performance & Memory Tuning][performance], which cover the *runtime*
    parameters (`divisions`, `num_moments`, precision, ...) set from the Python interface. This page
    describes what is fixed into the binary at **compile time**.

# Code Structure & Compilation Options

## Memory Architecture

The memory consumed by a KITEx calculation is governed by two independent mechanisms: the spatial
partitioning of the lattice (domain decomposition) and the temporal structure of the Chebyshev expansion
(moment blocking). These two mechanisms are controlled by different parameters, act on different data
structures, and can be tuned independently. This section explains both, and how they relate to one
another; [Performance & Memory Tuning][performance] provides the exact per-object memory-footprint
formulas.

### Spatial memory: domain decomposition and ghost regions

Setting [`#!python divisions=[nx,ny,(nz)]`][configuration-divisions] causes KITEx to spawn `nx*ny*(nz)`
OpenMP threads, each of which is assigned one rectangular sub-domain of the full lattice
(`length=[lx,ly,(lz)]`) and iterates the Chebyshev recursion independently on that sub-domain.

Because the Hamiltonian couples neighboring sites, a thread located near the edge of its sub-domain must
be able to read values that belong, physically, to a neighboring thread's sub-domain. This is the purpose
of **ghost regions**: each sub-domain is over-allocated with a halo of width `NGHOSTS` on every face
(`Ld[i] = ld[i] + 2*NGHOSTS`). At every Chebyshev iteration, `KPM_Vector::Exchange_Boundaries()`
synchronizes these halos: each thread copies its own boundary layer into a shared buffer, a barrier
ensures all threads have completed the copy, and each thread then reads its neighbors' data out of that
buffer into its own ghost region. This is implemented with OpenMP barriers and shared memory, not message
passing, since all threads reside in a single process.

The default value of `NGHOSTS` is not arbitrary. As stated in [tight-binding models][tb_model] and
[Disorder][disorder_doc], KITE's default build assumes that hopping terms — and disorder patterns, which
are themselves special hopping or on-site terms — connect unit cells no more than two lattice spacings
apart in any given direction. The ghost halo must be at least as deep as the longest-range hopping present
in the model, since a thread cannot otherwise access the site it needs to couple to across a sub-domain
boundary; `NGHOSTS = 2` is therefore the constant that encodes this maximum supported hopping range.
Models with longer-range hoppings (third-nearest-neighbor and beyond) require increasing `NGHOSTS` in
`Src/Generic.hpp` and recompiling KITEx, as described in [Compilation Options](#compilation-options) below.

`TILE` is a related but distinct constant: a cache-blocking granularity for the Hamiltonian-vector multiply
loops, unconnected to hopping range. It intersects domain decomposition through a single constraint,
`length[i] % (divisions[i] * TILE) == 0`, meaning each sub-domain's size must itself be a multiple of
`TILE`.

### Temporal memory: Chebyshev moment blocking

A separate memory cost arises for target functions that require a two-index correlation of Chebyshev
moments — specifically CondDC and CondOpt2 (implemented in `Gamma2D`/`Gamma3D`). Rather than retaining all
`num_moments` iteration vectors simultaneously, these calculations process moments in blocks of size
`MEMORY` and accumulate the result incrementally. `MEMORY` therefore governs a purely temporal axis of
memory consumption, entirely unrelated to the lattice's spatial partitioning.

### Independence of the two axes

Because the spatial and temporal mechanisms above are controlled by different constants and act on
different data, memory can be reduced along one axis without any effect on the other:

| Constant | Axis | Governs |
|---|---|---|
| `divisions` (runtime) | spatial | Number of threads and the partitioning of the lattice |
| `NGHOSTS` (compile-time, unguarded) | spatial | Halo depth; equivalently, the maximum supported hopping range |
| `TILE` (compile-time, guarded) | spatial | Cache-blocking granularity, and a divisibility constraint on partition size |
| `MEMORY` (compile-time, guarded) | temporal | Chebyshev-moment blocking size, applicable to CondDC/CondOpt2 only |

In practice, the dominant memory cost of a given calculation depends on which regime it falls into. For a
large lattice with a modest number of Chebyshev moments, spatial memory dominates, and reducing the degree
of domain decomposition (fewer, larger sub-domains) reduces the halo overhead relative to bulk memory. For
a calculation with a very large `num_moments` on CondDC or CondOpt2, temporal memory dominates instead, and
recompiling with a smaller `MEMORY` value is the applicable lever. Because the two axes are independent,
addressing one does not require any concession on the other.

## Architecture Overview

KITE is built from three independently-compiled components that communicate only through a shared
[HDF5 file][hdf5_structure]:

1. **Python interface** (`kite.py`, built on [Pybinding][pybinding]) constructs the lattice/Hamiltonian
   description and calculation settings, and writes them to a new `.h5` file.
2. **KITEx** (`Src/`) reads that file, executes the Chebyshev (KPM) recursion in parallel, and writes the
   computed moments back into the same file.
3. **KITE-tools** (`tools/Src/`) reads the moments back out and reconstructs physical quantities (DOS,
   conductivities, ...), writing `.dat` files.

Both C++ programs are built from the same root [`CMakeLists.txt`][cmakelists_gh] in a single
`cmake && make` invocation. `tools/CMakeLists.txt` is a second, independent copy of the same build logic,
retained so that KITE-tools can also be rebuilt as a standalone project (`cd tools && cmake . && make`),
which is the approach taken by `Dockerfile.full`. Because nothing enforces equivalence between the two
files, they can drift out of sync; both should be checked when modifying build flags.

## `Src/` — KITEx

| Directory | Contents |
|---|---|
| `Src/main.cpp` | Entry point. Reads the HDF5 configuration, determines the scalar type (`float`/`double`/`long double`, real or complex) and dimensionality (1D/2D/3D) requested, and dispatches to the corresponding `GlobalSimulation<T,D>` instantiation. |
| `Src/Generic.hpp` | Central header defining global compile-time constants (`MEMORY`, `TILE`, `DEBUG`, `VERBOSE`, ...) and the `verbose_message`/`debug_message`/`vverbose_message` logging macros. Included, directly or transitively, by nearly every other file. |
| `Src/Lattice/` | `Coordinates.*` (index/coordinate conversions) and `LatticeStructure.*`, the domain-decomposition engine described above: it partitions the lattice into per-thread sub-domains, computes ghost/halo sizing, and enforces the `length`/`divisions` divisibility rule. |
| `Src/Hamiltonian/` | `Hamiltonian.*` (base class, reads `/Hamiltonian/*` from the HDF5 file), `HamiltonianRegular.*` (periodic hoppings), `HamiltonianDefects.*` (structural/bond disorder), `HamiltonianVacancies.*` (site removal), `aux.*` (shared helpers). |
| `Src/Vector/` | `KPM_VectorBasis.*` (the underlying dense `Eigen::Matrix` storage), `KPM_Vector.*` together with `KPM_Vector2D.*`/`KPM_Vector3D.*` (dimension-specific Chebyshev iteration and `Exchange_Boundaries()` ghost synchronization). |
| `Src/Simulation/` | `Global.hpp` (the `GLOBAL_VARIABLES<T>` struct: cross-thread shared state, including the ghost buffer, running moment/gamma averages, and the `calculate_*` flags read from the HDF5 file), `GlobalSimulation.cpp` (opens the `#pragma omp parallel` region, one `Simulation<T,D>` per thread), `Simulation.*` (per-thread driver), and one `Simulation<Calculation>.cpp` file per target function: `SimulationDOS`, `SimulationCondDC`, `SimulationCondOpt`, `SimulationCondOpt2`, `SimulationARPES`, `SimulationLMU` (LDOS), `SimulationGaussianWavePacket`, `SimulationSingleShot`. |
| `Src/Tools/` | `myHDF5.*` (HDF5 C++ API read/write helpers; see [Editing an HDF5 file][hdf5_structure]), `Gamma1D/2D/3D.cpp` (the generic Chebyshev-moment accumulation kernels shared by several `Simulation*` files — for example, `Gamma2D` underlies `SimulationCondDC`), `ComplexTraits.*`, `Random.*`, `recursive_kpm.cpp`, `instantiate.hpp` (forces every scalar-type/dimension combination to be compiled in; see below), `messages.hpp` (the KITEx banner and flags text), and `queue.*` (string-formatting helpers only; there is no task queue in the codebase, since parallelism is implemented purely through `#pragma omp parallel`). |

## `tools/Src/` — KITE-tools

| Directory | Contents |
|---|---|
| `tools/Src/main.cpp` | CLI entry point; parses `--DOS`/`--CondDC`/etc. and their associated `-N`/`-M`/`-E`/... flags. |
| `tools/Src/Spectral/` | `dos.*`, `ldos.*`, `arpes.*` — spectral quantities reconstructed directly from Chebyshev moments. |
| `tools/Src/CondDC/` | `conductivity_dc.*`, `fill.cpp` — linear DC conductivity (Kubo-Bastin). |
| `tools/Src/OptCond_1order/` | `conductivity_optical.*` — linear (first-order) optical conductivity. |
| `tools/Src/OptCond_2order/` | `conductivity_2order.*`, together with `Gamma0/1/2/3.cpp` (general two-frequency response) and `Gamma0/1/2/3photo.cpp` (the degenerate photocurrent/shift-current response, selected with `-R -1`). |
| `tools/Src/Tools/` | `myHDF5.*` (read-only counterpart of KITEx's version), `parse_input.*` (CLI flag parsing), `calculate.*` (dispatches to the appropriate module based on flags), `functions.*`, `systemInfo.*`. |
| `tools/Src/macros.hpp` | KITE-tools' own, independent `DEBUG`/`VERBOSE` guards and `verbose_message`/`debug_message` macros, separate from those in `Src/Generic.hpp` (see below). |
| `tools/Src/compiletime_info.h.in` | Template for `compiletime_info.h`, generated by CMake's `configure_file()`; records the build machine name, operating system, and timestamp into the binary, reported by `tools/Src/Tools/systemInfo.cpp` via `--info`/`-i`. |

## Compilation Options

### CMake-level options

| Variable | Default | Effect |
|---|---|---|
| `CMAKE_BUILD_TYPE` | `Release` | Setting `-DCMAKE_BUILD_TYPE=Debug` adds `-DDEBUG=1` (via `add_definitions`, [`CMakeLists.txt:10-12`][cmakelists_gh]) and changes optimization flags. Because `add_definitions` applies to every target declared afterward in the same file, this affects both KITEx and KITE-tools when building from the root `CMakeLists.txt`. |
| `USE_SYSTEM_EIGEN` | `OFF` | Selects between the bundled `third_party/eigen3` (default) and a system installation located via `find_package(Eigen3)`. See [Installation][installation]. |

Two further compile-time choices exist but are not exposed as CMake options:

- **Compiler selection.** `CMakeLists.txt` hardcodes `set(CMAKE_C_COMPILER "gcc")` and
  `set(CMAKE_CXX_COMPILER "g++")` ([`CMakeLists.txt:2-3`][cmakelists_gh]). On macOS, these names resolve
  to Apple Clang, which lacks OpenMP support. Changing the compiler therefore requires editing these two
  lines directly (see the [verified MacPorts recipe][macports_recipe]); passing
  `-DCMAKE_CXX_COMPILER=...` on the command line has no effect, since the hardcoded `set()` in the file
  takes precedence.
- **`COMPILE_WAVEPACKET`.** This is set automatically by CMake — `1` if
  `CMAKE_CXX_COMPILER_VERSION >= 8.0.0`, otherwise `0` ([`CMakeLists.txt:66-71`][cmakelists_gh]) — and
  gates whether Gaussian wavepacket propagation is compiled in. There is no supported way to force this
  on with an older compiler.

### Preprocessor constants in `Src/Generic.hpp`

The following constants have no corresponding CMake option. They may be changed either by editing
`Src/Generic.hpp` directly, or by passing extra flags through `CMAKE_CXX_FLAGS`, for example:

```bash
cmake -DCMAKE_CXX_FLAGS="-DMEMORY=32 -DTILE=16" ..
```

This mechanism relies on the `#ifndef` guard present in the definition of each constant: a command-line
`-D` definition is already in effect by the time `Src/Generic.hpp` is processed, so the header's own
`#define` is skipped.

| Constant | Default | Overridable via `-D` | Effect |
|---|---|---|---|
| `MEMORY` | `16` | Yes | Number of Chebyshev columns held simultaneously in `Gamma2D`/`Gamma3D` (used by CondDC and CondOpt2); see [Performance & Memory Tuning][performance] for the exact memory-footprint formula. A larger value produces fewer, larger moment-blocking passes, trading memory for speed; a smaller value trades speed for memory. |
| `TILE` | `8` | Yes | Cache-blocking tile size used throughout the indexing in `Src/Vector/KPM_Vector2D.cpp`/`KPM_Vector3D.cpp`. This also governs which lattice sizes are accepted at runtime, since `LatticeStructure::test_divisibility()` requires `length[i] % (divisions[i] * TILE) == 0`. |
| `DEBUG` | `0` | Yes (or via `CMAKE_BUILD_TYPE=Debug`) | Enables `debug_message(...)` output. |
| `VERBOSE` | `1` | Yes | Enables the startup banner and `verbose_message(...)` progress output. |
| `ESTIMATE_TIME` | `0` | Yes | Defined and guarded, but not read anywhere else in the current codebase; the sole call site that would print it, in `Src/Tools/messages.hpp`, is commented out. |
| `COMPILE_WAVEPACKET` | `1` | In principle, though CMake always sets this explicitly; overriding it would also require bypassing that `add_definitions` call. | Gates whether `Simulation::Gaussian_Wave_Packet()` is compiled in. |

!!! Warning "Four constants that are not overridable despite appearing alongside those that are"

    `PATTERNS` (`4`), `NGHOSTS` (`2`), `VVERBOSE` (`0`), and `SSPRINT` (`0`) are defined **without** an
    `#ifndef` guard ([`Src/Generic.hpp:65-68`][genericheader_gh]). Passing, for example, `-DNGHOSTS=3` on
    the command line does not produce a compilation error; the compiler emits a `"NGHOSTS" redefined`
    warning, and the value hardcoded in `Src/Generic.hpp` takes precedence regardless. Changing any of
    these four constants requires editing `Src/Generic.hpp` directly and recompiling.

    These four constants are not of equal significance:

    - **`NGHOSTS`** is genuinely load-bearing (see [Memory Architecture](#memory-architecture) above for
      its physical meaning), and is used directly in approximately 90 locations across
      `Src/Lattice/LatticeStructure.cpp`, `Src/Vector/KPM_Vector2D.cpp`/`KPM_Vector3D.cpp`, and
      `Src/Hamiltonian/HamiltonianDefects.cpp` — as loop bounds
      (`for(i = NGHOSTS; i < Ld[d] - NGHOSTS; ...)`), boundary-exchange buffer indexing, and ghost-buffer
      size calculations. Increasing this constant to support longer-range hopping models requires
      auditing those call sites, as the change is not risk-free.
    - **`PATTERNS`** is unused in the current codebase — a repository-wide search finds only its own
      definition, with no call sites.
    - `VVERBOSE`/`SSPRINT` are minor debug switches (very verbose tracing, and an internal print-frequency
      toggle, respectively) with limited impact if changed.

### Independent debug/verbose flags in KITE-tools

`tools/Src/macros.hpp` redeclares `DEBUG` and `VERBOSE` independently of `Src/Generic.hpp`
(`tools/Src/macros.hpp:11-16`). Because the root `CMakeLists.txt`'s `add_definitions(-DDEBUG=1)` for a
Debug build applies globally to every target declared afterward, building the entire project with
`-DCMAKE_BUILD_TYPE=Debug` enables debug output in both KITEx and KITE-tools. If `-DDEBUG=1` is instead
supplied only while compiling one of the two executables — for example, via the standalone
`tools/CMakeLists.txt` build — only that executable is affected.

### Runtime versus compile-time parameters

`divisions`, `length`, `boundaries`, `precision`, `is_complex`, `num_moments`, `num_random`,
`num_disorder`, and similar quantities are runtime parameters, not compile-time options: they are set in
the Python `kite.Configuration()`/`kite.Calculation()` call and stored in the HDF5 file, from which KITEx
reads them at runtime. Every combination of scalar type and dimensionality is pre-compiled into the binary
via `Src/Tools/instantiate.hpp` (`float`/`double`/`long double`, real and complex, across 1D/2D/3D — 18
instantiations in total), so changing `precision` or `is_complex` never requires a rebuild. Only `MEMORY`,
`TILE`, and the four constants listed above are fixed at compile time.

### Documentation inconsistency

The runtime banner in `Src/Tools/messages.hpp` instructs users to "set DEBUG to 1 in the Makefile." This
text predates the current CMake-based build system; there is no plain Makefile in the project today, and
the mechanisms described above are the applicable ones.

### Installation via `make install`

Both `CMakeLists.txt` files register `install(TARGETS ... DESTINATION bin)` for their respective
executables, so `make install` (following `cmake ..`) copies `KITEx`/`KITE-tools` into
`${CMAKE_INSTALL_PREFIX}/bin` (`/usr/local/bin` by default). This is the mechanism used by
`Dockerfile.full`.

[performance]: performance.md
[hdf5_structure]: editing_hdf_files.md
[installation]: ../installation.md
[macports_recipe]: ../installation.md#23-verified-macports-recipe
[pybinding]: https://docs.pybinding.site/en/stable
[cmakelists_gh]: https://github.com/quantum-kite/kite/blob/master/CMakeLists.txt
[genericheader_gh]: https://github.com/quantum-kite/kite/blob/master/Src/Generic.hpp
[settings]: settings.md
[tb_model]: tb_model.md
[disorder_doc]: disorder.md
[configuration-divisions]: ../api/kite.md#configuration-divisions
