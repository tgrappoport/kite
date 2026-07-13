This directory contains a pruned copy of [Eigen](https://eigen.tuxfamily.org) 3.4.0,
vendored so that KITE does not depend on the host system having a compatible
Eigen3 install (a recurring source of cross-machine build issues).

* **Source:** https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.gz
* **Version:** 3.4.0
* **License:** MPL2 (see `COPYING.MPL2`; a few files are BSD-licensed, see `COPYING.BSD`)

Only the header-only `Eigen/` module directory is vendored. KITE only ever
includes `<Eigen/Dense>` (confirmed by grepping the whole codebase), so
`unsupported/`, `test/`, `bench/`, `demos/`, `blas/`, `lapack/`, `doc/`,
`scripts/`, `cmake/`, `ci/`, `debug/`, `failtest/`, and Eigen's own build
files were dropped from the upstream release tarball.

To update: download a newer Eigen release tarball, replace the `Eigen/`
directory here with the new one, and update the version/source above.
