## What is an HDF file?

The following description of an HDF file has been adapted from [HDF](https://support.hdfgroup.org/documentation/index.html):

Hierarchical Data Format 5 (HDF5) is a unique open source technology suite for managing data collections of all sizes and complexity. HDF5 has features of other formats, but it can do much more.
HDF5 is similar to XML in that HDF5 files are self-describing and allow users to specify complex data relationships and dependencies.
In contrast to XML documents, HDF5 files can contain binary data (in many representations) and allow direct access to part of the file without first parsing the entire contents.

HDF5 also allows hierarchical data objects to be expressed in a natural manner (similar to directories and files), in contrast to the tables in a relational database.
Whereas relational databases support tables, HDF5 supports n-dimensional datasets and each element in the dataset may itself be a complex object.
Relational databases offer excellent support for queries based on field matching,
but are not well-suited for sequentially processing all records in the database or for selecting a subset of the data based on coordinate-style lookup.

## The structure of KITE's HDF5 file

The same `.h5` file is passed through KITE's whole pipeline: the Python interface ([`#!python kite.Configuration`][configuration]/[`#!python kite.Calculation`][calculation], via `#!python kite.py`) creates it, [KITEx][kitex] reads the lattice/calculation settings from it and writes the raw Chebyshev moments back into it, and [KITE-tools][kitetools] opens it read-only to reconstruct physical quantities. Knowing the exact layout lets you script around KITE-tools entirely if you want to.

There is no top-level wrapper group — everything hangs directly off the file root `#!python /`:

```text
/
├── IS_COMPLEX                 (u4)     0/1, from is_complex
├── PRECISION                  (u4)     0=float, 1=double, 2=long double
├── L                          (u4[dim])   lattice repetitions per direction
├── DIM                        (u4)     lattice dimensionality (1/2/3)
├── Boundaries                 (u4[dim])   0=open, 1=periodic/fixed-twist, 2=random-twist
├── BoundaryTwists              (f64[dim])  fixed twist-angle phases
├── Divisions                  (u4[dim])   domain decomposition, i.e. divisions=[nx,ny,(nz)]
├── LattVectors                 (f64[dim,dim])
├── OrbPositions                (f64[Norb,dim])
├── NOrbitals                  (u4)     total number of orbitals
├── EnergyScale                 (f64)    Chebyshev rescaling factor δε
├── EnergyShift                 (f64)    Chebyshev rescaling shift ε₀
├── Hamiltonian/
│   ├── NHoppings               (u4[Norb])
│   ├── d, Hoppings                       hopping distances/values (already rescaled by EnergyScale)
│   ├── CustomLocalEnergy, PrintCustomLocalEnergy
│   ├── MagneticFieldMul        (u4)     present only if a magnetic field/flux was set
│   ├── Disorder/                        Anderson-type onsite disorder, if any
│   │   ├── OnsiteDisorderModelType, OrbitalNum
│   │   └── OnsiteDisorderMeanValue, OnsiteDisorderMeanStdv
│   ├── Vacancy/Type{N}/                 one subgroup per vacancy type
│   │   └── Orbitals, FixPosition, Concentration, NumOrbitals
│   └── StructuralDisorder/Type{N}/      one subgroup per bond/structural-disorder type
│       ├── FixPosition, Concentration
│       ├── NumBondDisorder, NumOnsiteDisorder
│       ├── NodeFrom, NodeTo, NodeOnsite, NumNodes, NodePosition
│       └── U0, Hopping
└── Calculation/                         only the sub-groups you actually requested exist
    ├── dos/                    NumMoments, NumRandoms, NumPoints, NumDisorder, MU (written by KITEx)
    ├── ldos/                   NumMoments, Energy, Orbitals, FixPosition, NumDisorder, lMU
    ├── arpes/                  NumMoments, k_vector, NumDisorder, OrbitalWeights, kMU
    ├── gaussian_wave_packet/   NumMoments, NumPoints, NumDisorder, mean_value, ProbingPoint,
    │                           width, spinor, k_vector, timestep, Sx, Sy, Sz, Id
    ├── conductivity_dc/        NumMoments, NumRandoms, NumPoints, NumDisorder, Temperature,
    │                           Direction, Gamma<dir>   (dir = 2-letter code, e.g. "xx", "xy")
    ├── conductivity_optical/   same fields as conductivity_dc, plus Gamma<dir> and Lambda<dir>
    ├── conductivity_optical_nonlinear/  adds `Special` (ratio/photocurrent flag),
    │                           Gamma0<dir>, Gamma1<dir>, Gamma2<dir>, Gamma3<dir>  (dir = 3-letter code)
    └── singleshot_conductivity_dc/  NumMoments, NumRandoms, NumDisorder, Energy, Gamma,
                                Direction, PreserveDisorder, SingleShot (the actual conductivity values)
```

Everything here is a **dataset** — `kite.py` never uses HDF5 attributes, so there is nothing to find under `.attrs` on any object.

!!! Warning "Complex numbers are stored as compound types, not native complex"

    Datasets holding complex Chebyshev moments (`MU`, `Gamma<dir>`, `lMU`, `kMU`, ...) are **not** written
    as HDF5 native complex data. [KITEx][kitex] (`Src/Tools/myHDF5.cpp`) reads/writes them as an HDF5
    *compound type* with two members, `#!python "r"` and `#!python "i"`, each of the same float type as
    `PRECISION` selects. If you write such a dataset from Python with plain `#!python h5py`, don't rely on
    h5py's native complex support — build the matching compound dtype explicitly:

    ``` python linenums="1"
    import numpy as np
    import h5py

    # matches PRECISION=1 (double) — use np.float32/np.float128 for the other precisions
    complex_t = np.dtype([('r', np.float64), ('i', np.float64)])

    f = h5py.File('archive.h5', 'r+')
    data = np.zeros(100, dtype=complex_t)
    data['r'] = my_real_part
    data['i'] = my_imag_part
    f['Calculation/conductivity_dc'].create_dataset('Gammaxx', data=data)
    ```

## Editing the file

Leveraging its underlying Chebyshev approach, KITE can easily recalculate a physical quantity for different choices of parameters at the post-processing level, i.e. without the need for recalculating Chebyshev moments.
As explained in the [Post-processing tools documentation](postprocessing.md), this can be done via several options available in [KITE-tools][kitetools]. Here, we discuss an alternative (more advanced) approach, based on the editing of the HDF file. 
Suppose we would like to change the post-processing parameters specified when first creating the HDF file (e.g., the temperature or number of energy points of a conductivity calculation). For that purpose, we provide a simple Python script that rewrites specific parts of our .h5 files.
As discussed above, the .h5 contains hierarchical data objects that are similar to the structure of directories and files.

When modifying a parameter, such as temperature, we begin by locating it in the HDF file.
The script below describes how to list and edit the parameters in an HDF file.

``` python linenums="1"
file_name = 'archive.h5'
f = h5py.File(file_name, 'r+')     # open the file

# List all groups
print('All groups')
for key in f.keys():  # Names of the groups in HDF5 file.
    print(key)
print()

# Get the HDF5 group
group = f['Calculation']

# Checkout what keys are inside that group.
print('Single group')
for key in group.keys():
    print(key)
print()
#if you want to modify other quantity, check de list and change the subgroup below
# Get the HDF5 subgroup
subgroup = group['conductivity_dc']

# Checkout what keys are inside that subgroup.
print('Subgroup')
for key in subgroup.keys():
    print(key)
print()

new_value = 70
data = subgroup['Temperature']  # load the data
data[...] = new_value  # assign new values to data
f.close()  # close the file

# To confirm the changes were properly made and saved:

f1 = h5py.File(file_name, 'r')
print(np.allclose(f1['Calculation/conductivity_dc/Temperature'].value, new_value))
```


[kitex]: ../api/kitex.md
[kitetools]: ../api/kite-tools.md
[configuration]: ../api/kite.md#configuration
[calculation]: calculation.md