!!! Info

    [Section 0][ground_rules] and [Section 3][settings] already explain the *physics* behind
    [`#!python divisions`][configuration-divisions], `#!python num_moments`, `#!python num_random` and
    `#!python num_disorder`. This page instead documents what actually happens **inside [KITEx][kitex]**
    when you pick those numbers, so that you can reason about — and control — the memory footprint of a
    calculation, especially for large lattices.

# Domain Decomposition & Memory Usage

## How the domain decomposition actually works

[KITEx][kitex] parallelizes over shared-memory threads with **OpenMP**, not MPI. Setting
[`#!python divisions=[nx,ny,(nz)]`][configuration-divisions] makes KITE spawn `#!python nx*ny*(nz)`
OpenMP threads (one per sub-domain) inside a single `#pragma omp parallel` region; each thread owns one
`Simulation` instance and iterates the Chebyshev recursion independently on its own slice of the lattice.

The full lattice of size `#!python length=[lx,ly,(lz)]` is cut into equal sub-domains of size
`#!python lx/nx, ly/ny, (lz/nz)`. Two internal compile-time constants control the geometry of each slice
(`Src/Generic.hpp`):

* `#!cpp TILE = 8` — the block size used for cache-friendly memory access.
* `#!cpp NGHOSTS = 2` — the width (in unit cells) of the "ghost" halo added around every sub-domain so a
  thread can evaluate the Hamiltonian near its boundary without touching another thread's memory directly.

This is why KITE requires the lateral size of each partition to be an exact multiple of `TILE`: at startup
`LatticeStructure<D>::test_divisibility()` checks `#!cpp Lt[i] % (nd[i] * TILE) != 0` for every direction and
aborts with an explicit error if it fails. In practice: **`lx/nx`, `ly/ny`, `lz/nz` must each be a multiple of
8**, not merely an integer.

Each sub-domain therefore actually allocates `#!python ld[i] + 2*NGHOSTS` sites per direction (`ld[i]` being the
"real" partition size) — the ghost layers are extra memory, not shared with neighbours. The one exception is
the boundary-exchange step itself: at every Chebyshev iteration, `KPM_Vector::Exchange_Boundaries()` copies
each thread's own edge layer into one **shared** buffer (`GLOBAL_VARIABLES::ghosts`, sized by
`LatticeStructure::get_BorderSize()`), barriers, and then reads its neighbours' slices out of that same
buffer — so the halo-exchange buffer scales with the sub-domain **perimeter** (2D) or **face area** (3D)
times the number of orbitals, not with its volume.

!!! Warning "The divisions vs. memory/scaling trade-off"

    Increasing `#!python nx*ny*(nz)` gives you more parallelism, but each extra division adds a fixed
    `2*NGHOSTS`-wide halo to every sub-domain. For a fixed total lattice size, more (smaller) partitions
    means the ghost regions become a *larger fraction* of each partition's memory and more time is spent
    exchanging boundaries relative to bulk work. There's no free lunch here — pick the coarsest
    decomposition that still uses all your available cores.

## What actually costs memory: the `KPM_Vector`

Every Chebyshev vector kept during a calculation is a dense matrix,
`#!cpp v = Eigen::Matrix<T,Dynamic,Dynamic>::Zero(Sized, memory)`, where:

* `#!cpp Sized = (∏ᵢ (ld[i] + 2*NGHOSTS)) * NOrbitals` — the *padded* (ghost-inclusive) size of one thread's
  sub-domain, in scalars;
* `#!cpp memory` is simply how many Chebyshev-iteration columns that particular vector needs to keep around
  at once (passed to the `KPM_Vector` constructor);
* `#!cpp T` is the scalar type selected by [`#!python precision`][configuration-precision] and
  [`#!python is_complex`][configuration-is_complex] — `float` (4B), `double` (8B) or `long double` (16B),
  doubled again if complex.

So, per `KPM_Vector` instance: **`bytes ≈ Sized × memory_columns × sizeof(T)`**. The total memory of a
calculation is this formula summed over however many `KPM_Vector` instances are alive *simultaneously* —
and that count depends on which target function you're computing:

| Calculation                          | Live `KPM_Vector`s (constructor arg = columns)                       | Total columns          |
|---------------------------------------|------------------------------------------------------------------------|-------------------------|
| DOS (`Gamma1D`)                       | `kpm0(1)`, `kpm1(2)`                                                    | 3                       |
| CondDC (`Gamma2D`)                    | `kpm0(1)`, `kpm1(2)`, `kpm2(MEMORY)`, `kpm3(MEMORY)`                    | `2·MEMORY + 3` = **35** |
| CondOpt2 / nonlinear (`Gamma3D`)      | `kpm0(1)`, `kpm_Vn(2)`, `kpm_VnV(MEMORY)`, `kpm_p(2)`, `kpm_pVm(MEMORY)` | `2·MEMORY + 5` = **37** |
| SingleShot, ARPES, LDOS, wave-packet  | a handful of `mem ∈ {1,2}` vectors                                      | ~3–9                    |

`#!cpp MEMORY` is a **compile-time constant, default 16** (`Src/Generic.hpp`, comment: *"number of KPM
vectors stored in memory while calculating Gamma2D"*). It exists precisely so that CondDC and CondOpt2 —
the two calculation types whose inner double-loop over Chebyshev moments is blocked in chunks of `MEMORY`
— don't have to keep all `num_moments` columns resident at once; they process `MEMORY` moments at a time
and accumulate the result.

!!! Info "num_random and num_disorder are free, memory-wise"

    Averaging over random vectors (`#!python num_random`) or disorder realizations (`#!python num_disorder`)
    does **not** allocate extra `KPM_Vector` memory. Both are outer loops that reuse the very same vectors
    and fold each new sample into a running average in place
    (`gamma += (new_estimate - gamma) / (average + 1)`). You can raise these to improve statistics without
    growing memory usage.

## Practical tricks for reducing memory footprint

1. **Lower precision.** Switching [`#!python precision`][configuration-precision] from `2` (long double) →
   `1` (double) → `0` (float) scales `sizeof(T)` down by up to 4×. This is a configuration choice in
   `kite.py`, not a recompile — all three precisions are pre-instantiated in the binary.
2. **Use `#!python is_complex=False`** whenever the Hamiltonian is real-symmetric — this halves `sizeof(T)`
   again on top of the precision choice.
3. **Recompile with a smaller `#!cpp -DMEMORY=N`** if you specifically run CondDC/CondOpt2 on very large
   lattices and are memory-bound rather than compute-bound. This directly shrinks the `2·MEMORY` term above.

    !!! Warning "Undocumented divisibility assumption"

        The moment-blocking loops in `Gamma2D`/`Gamma3D` are written as
        `#!cpp for(n = 0; n < N_moments; n += MEMORY)` with no runtime check that `num_moments` is a
        multiple of `MEMORY`. If you recompile with a custom `MEMORY` (or pick a `num_moments` that isn't a
        multiple of 16 with the default build), double check your results — there is no assertion guarding
        this anywhere in the live code path (only a leftover check exists in commented-out code in
        `Src/Tools/recursive_kpm.cpp`).

4. **Don't over-subdivide.** As explained above, `divisions` trades ghost/halo overhead against
   parallelism — pick the smallest `nx*ny*(nz)` that saturates your available cores, rather than the largest
   one your lattice size allows.
5. **Disorder/vacancies/defects are cheap.** `HamiltonianDefects`/`HamiltonianVacancies` store extra arrays
   sized by the *number of defects/vacancies*, not by lattice volume, so structural disorder is not a
   significant memory driver unless the defect density is extremely high. The base sparse Hamiltonian itself
   is stored per-orbital (hoppings and distances arrays sized by orbital count × max neighbours), independent
   of the domain decomposition.

[ground_rules]: optimization.md
[settings]: settings.md
[kitex]: ../api/kitex.md
[configuration-divisions]: ../api/kite.md#configuration-divisions
[configuration-precision]: ../api/kite.md#configuration-precision
[configuration-is_complex]: ../api/kite.md#configuration-is_complex
