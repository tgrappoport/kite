# KITE TODO Tracker

Distilled from `KITE_ Version 1.2 (2023).pdf` (an internal team notes document, undated content spanning
roughly 2023-2024) plus items raised in conversation. Kept outside `docs/` — internal tracking only, never
built or published.

The source PDF mixed genuinely actionable items with a lot of meeting-logistics/personnel discussion; only
the technical/documentation items are carried over here. Status column reflects what's true as of
2026-07-14 on the `tgrappoport/kite` fork — re-verify against upstream `quantum-kite/kite` before assuming
these statuses hold there too.

## Dependencies / install pain points

| Item | Status |
|---|---|
| Eigen3 version/path issues across machines | **Fixed** this session — vendored under `third_party/eigen3/`, see commit `71b70db`. |
| HDF5 C++ API / version issues across machines | **Mitigated** — verified, tested MacPorts recipe added to `installation.md` §2.3 (commit `71b70db`). Homebrew path in the docs is still the older, untested recipe. |
| **h5py version/compatibility issues** | **Open.** Recurring problem reported (2026-07-13/14) — not yet characterized or documented. Need to pin down: which h5py versions are known-good/known-bad, and whether it's an ABI issue (h5py bundling its own HDF5 vs. linking system HDF5) or an API-compatibility issue. Not yet added to `installation.md`. |
| Original PDF's "complete refactor" plan (auto-download Eigen/HDF5 if not found, pip-installable with precompiled binaries) | Not implemented on this fork. The Eigen vendoring done this session is a lighter-weight version of the same idea; HDF5 (a compiled library, not header-only) still requires a system install. |

## Documentation TODOs from the PDF

| Item | Status |
|---|---|
| "NGHOSTS need to be documented!" (AF) | **Done** this session — `documentation/code_structure.md`, including the full explanation of why it defaults to 2 and its relation to `TILE`/`MEMORY`. |
| Rules of Thumb: clarify "100/η" (too demanding), suggest "~10/η" | **Already resolved** — current `optimization.md` already uses $M \gtrsim 10\,\delta\varepsilon/\eta$, not 100. (Unclear when this was changed; predates this session.) |
| Document the process scripts in `tools/` (`process_single_shot.py`, `process_arpes.py`, etc.) | **Partially done.** `process_single_shot.py` is documented in `postprocessing.md`. `process_arpes.py` is now covered by the new `documentation/examples/spectral_function.md` (this session), but there's no single place listing all the `tools/`-directory helper scripts together. |
| Documentation for Gaussian wavepacket [low priority] | **Open.** Not covered by any page added this session. |
| Example with open boundary conditions (nanoribbon; Fu-Kane-Mele 3D TI slab) | **Open.** |
| Automatic spectrum range detection "sometimes segfaults" | **Open, and possibly related to a finding from this session**: automatic scaling was found to significantly under-estimate the true bandwidth for a multi-orbital TMD model (independent of disorder), producing divergent Chebyshev moments rather than a crash — see `2026-07-13-session-summary.md` §4. Worth checking whether these are the same underlying root cause. |
| Add to API section [needs deciding what exactly] | **Open**, vague in the source notes — needs clarification of scope before actioning. |
| Header of Python example scripts need update (old copyright) | **Still open** — `examples/*.py` still carry a generic "Copyright 2020/2022, KITE" header; unclear what the intended replacement text is. |
| KITEx output messages could be clearer (e.g. "Calculating DOS. Done." -> something indicating moments are ready for post-processing) | **Open** — cosmetic, `Src/Tools/messages.hpp` / per-calculation "Calculating X." prints. |
| `disorder.md`: "Deterministic disorder" may be superfluous (just a uniform onsite shift) | **Open design question**, not a doc fix — needs a decision from the team before documenting either way. |
| Single-shot post-processing doc bug (wrong column extracted in example) | Reported as fixed by Tatiana in the original notes; not independently re-verified this session. |

## Known bugs (from the PDF)

| Item | Status |
|---|---|
| DOS calculation with `precision=2` (long double) fails for a simple bilayer system | **Open** — not reproduced or investigated this session. Original note references "simulation #14606536," contact Aires for details. |
| Automatic spectrum range segfault | See above — possibly related to the automatic-scaling under-estimation found this session. |

## Examples folder (from the PDF, lower priority)

Several suggested renames/reorganizations of `examples/*.py` for clarity (e.g. `dccond_phosphorene.py` should
be renamed to make clear it computes single-shot DC conductivity; put beginner-friendly square-lattice
examples in a dedicated tutorial folder; `ldos_graphene.py` should be renamed since it's really a structural
disorder example). Not actioned this session — repo-organization work, not documentation content.

## Not carried over from the source PDF

Meeting-logistics, funding, hiring, and personnel-related discussion (multiple meeting transcripts from
March–June 2024) was intentionally omitted from this tracker — not relevant to technical/documentation
tracking, and includes sensitive discussion about specific individuals' circumstances that doesn't belong
in a repository file. The original PDF remains the source of record for that material if needed.

The KITE v1.2/v1.3 feature roadmap (many-body extension, generic operator/vertex framework for response
functions, TILE cache-optimization notes, Kubo-Greenwood option, etc.) was also omitted here as it's a
development roadmap rather than a documentation TODO — worth its own tracking page if/when that work is
picked up.
