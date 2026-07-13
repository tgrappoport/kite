""" Monolayer TMD, 3-band model (ARPES / spectral function)

    ##########################################################################
    #                         Copyright 2020/2022, KITE                      #
    #                         Home page: quantum-kite.com                    #
    ##########################################################################

    Units: Energy in eV, Length in angstrom
    Lattice: Triangular (one metal site per unit cell, 3 d-orbitals: dz2, dxy, dx2-y2)
    Configuration: Periodic boundary conditions, double precision,
                   manual scaling, size of the system 128x128, with domain decomposition (nx=ny=2)
    Calculation type: one-particle spectral function of relevance to ARPES
    Reference for the tight-binding parameters: Liu et al., Phys. Rev. B 88, 085433 (2013);
    erratum Phys. Rev. B 89, 039901 (2014).
    Last updated: 13/07/2026
"""

import pybinding as pb
import kite
import sys
import numpy as np

# Nearest-neighbor 3-band tight-binding parameters (GGA), Liu et al.
# [a, z_XX, e1, e2, t0, t1, t2, t11, t12, t22, lambda_soc] -- lambda_soc is unused here (no SOC).
_LIU_TMD_1N_GGA = {
    "MoS2": [3.190, 3.130, 1.046, 2.104, -0.184, 0.401, 0.507, 0.218, 0.338, 0.057, 0.073],
}


def _hopping_matrices(v0, v1, v2, v11, v12, v22):
    """The three nearest-neighbor hopping matrices (one per lattice direction) for the
    3-band (dz2, dxy, dx2-y2) model, in the basis fixed by the lattice vectors used below."""
    rt3 = np.sqrt(3)
    h1 = [[v0, -v1, v2],
          [v1, v11, -v12],
          [v2, v12, v22]]
    h2 = [[v0, 0.5 * v1 + rt3 / 2 * v2, rt3 / 2 * v1 - 0.5 * v2],
          [-0.5 * v1 + rt3 / 2 * v2, 0.25 * v11 + 0.75 * v22, rt3 / 4 * (v11 - v22) - v12],
          [-rt3 / 2 * v1 - 0.5 * v2, rt3 / 4 * (v11 - v22) + v12, 0.75 * v11 + 0.25 * v22]]
    h3 = [[v0, -0.5 * v1 - rt3 / 2 * v2, rt3 / 2 * v1 - 0.5 * v2],
          [0.5 * v1 - rt3 / 2 * v2, 0.25 * v11 + 0.75 * v22, rt3 / 4 * (v22 - v11) + v12],
          [-rt3 / 2 * v1 - 0.5 * v2, rt3 / 4 * (v22 - v11) - v12, 0.75 * v11 + 0.25 * v22]]
    return [h1, h2, h3]


def tmd_monolayer(name="MoS2"):
    """Build a monolayer group-6 TMD lattice for the nearest-neighbor 3-band model.

    Each of the 3 d-orbitals (dz2, dxy, dx2-y2) is added as its own named sublattice
    ('Mo_0', 'Mo_1', 'Mo_2'), all at the same position, connected by explicit scalar
    hoppings between every orbital pair. This is the recommended construction for
    multi-orbital sites in KITE, rather than bundling several orbitals into one
    sublattice with dense hopping matrices.
    """
    a, z_XX, e1, e2, t0, t1, t2, t11, t12, t22, lambda_soc = _LIU_TMD_1N_GGA[name]

    lat = pb.Lattice(a1=[a, 0], a2=[a / 2, a * np.sqrt(3) / 2])

    subs = ["Mo_0", "Mo_1", "Mo_2"]  # dz2, dxy, dx2-y2
    lat.add_sublattices(
        (subs[0], [0, 0], e1),
        (subs[1], [0, 0], e2),
        (subs[2], [0, 0], e2),
    )

    vector_1N = [[1, 0], [0, -1], [1, -1]]
    matrices = _hopping_matrices(t0, t1, t2, t11, t12, t22)
    for direction, matrix in zip(vector_1N, matrices):
        for i in range(3):
            for j in range(3):
                val = matrix[i][j]
                if abs(val) > 1e-8:
                    lat.add_hoppings((direction, subs[i], subs[j], val))

    return lat, a


def main():
    # Simulation parameters
    moments = 512
    nx = ny = 2
    lx = ly = 128

    lattice, a = tmd_monolayer("MoS2")

    # Path in k-space: K -> Gamma -> K', passing through both inequivalent valleys
    # (see the spectral-function documentation for why K and K' are inequivalent
    # here, and for the general, orientation-independent way to find them via
    # lattice.brillouin_zone()). These corner formulas are specific to the
    # a1=[a,0], a2=[a/2, a*sqrt(3)/2] convention used above.
    Gamma = np.array([0, 0])
    K = np.array([4 * np.pi / (3 * a), 0])
    Kprime = np.array([2 * np.pi / (3 * a), 2 * np.pi / (a * np.sqrt(3))])
    dk = 0.1
    k_path = pb.results.make_path(K, Gamma, Kprime, step=dk)

    # One weight per orbital (3 named sublattices here, each single-orbital).
    weights = [1, 1, 1]

    # Manual spectrum range, comfortably covering the true bandwidth of this
    # model (recommended for multi-orbital models generally, rather than
    # relying on automatic scaling).
    configuration = kite.Configuration(
        divisions=[nx, ny],
        length=[lx, ly],
        boundaries=["periodic", "periodic"],
        is_complex=True,
        precision=1,
        spectrum_range=[-2, 4])

    calculation = kite.Calculation(configuration)
    calculation.arpes(
        k_vector=k_path,
        num_moments=moments,
        weight=weights,
        num_disorder=1)

    output_file = "arpes_tmd-output.h5"
    kite.config_system(lattice, configuration, calculation, filename=output_file)
    return output_file


if __name__ == "__main__":
    hdf5_file = main()  # generate the Configuration file

    if len(sys.argv) > 1 and sys.argv[1] == "complete":
        import run_all_examples as ra
        import process_arpes as pa
        ra.run_calculation(hdf5_file)
        ra.run_tools(hdf5_file, options="--ARPES -K jackson -S")
        pa.process_arpes("arpes.dat")
