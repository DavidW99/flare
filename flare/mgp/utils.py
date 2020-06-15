import numpy as np

from numpy import array
from numba import njit
from math import exp, floor
from typing import Callable

from flare.env import AtomicEnvironment
from flare.kernels.cutoffs import quadratic_cutoff
from flare.kernels.utils import str_to_kernel_set as stks
from flare.parameters import Parameters

from flare.mgp.grid_kernels_3b import grid_kernel, grid_kernel_sephyps


def str_to_mapped_kernel(name: str, component: str = "sc",
                         hyps_mask: dict = None):
    """
    return kernels and kernel gradient function base on a string.
    If it contains 'sc', it will use the kernel in sc module;
    otherwise, it uses the kernel in mc_simple;
    if sc is not included and multihyps is True,
    it will use the kernel in mc_sephyps module
    otherwise, it will use the kernel in the sc module

    Args:

    name (str): name for kernels. example: "2+3mc"
    multihyps (bool, optional): True for using multiple hyperparameter groups

    :return: mapped kernel function, kernel gradient, energy kernel,
             energy_and_force kernel

    """

    multihyps = True
    if hyps_mask is None:
        multihyps = False
    elif hyps_mask['nspecie'] == 1:
        multihyps = False

    # b2 = Two body in use, b3 = Three body in use
    b2 = False
    many = False
    b3 = False
    for s in ['3', 'three']:
        if s in name.lower() or s == name.lower():
            b3 = True

    if b3:
         if multihyps:
             return grid_kernel_sephyps
         else:
             return grid_kernel
    else:
        raise NotImplementedError("mapped kernel for two-body and manybody kernels "
                                  "are not implemented")

def get_kernel_term(GP, term):
    """
    Args
        term (str): 'twobody' or 'threebody'
    """
    kernel, _, ek, efk = stks([term], GP.component, GP.hyps_mask)

    hyps, cutoffs, hyps_mask = Parameters.get_component_mask(GP.hyps_mask, term, hyps=GP.hyps)

    return (kernel, ek, efk, cutoffs, hyps, hyps_mask)



@njit
def get_bonds(ctype, etypes, bond_array):
    exist_species = []
    bond_lengths = []
    bond_dirs = []
    for i in range(len(bond_array)):
        bond = bond_array[i]
        if ctype <= etypes[i]:
            spc = [ctype, etypes[i]]
            b_dir = bond[1:]
        else:
            spc = [etypes[i], ctype]
            b_dir = bond[1:]

        if spc in exist_species:
            ind = exist_species.index(spc)
            bond_lengths[ind].append([bond[0]])
            bond_dirs[ind].append(b_dir)
        else:
            exist_species.append(spc)
            bond_lengths.append([[bond[0]]])
            bond_dirs.append([b_dir])
    return exist_species, bond_lengths, bond_dirs


@njit
def get_triplets(ctype, etypes, bond_array, cross_bond_inds,
                 cross_bond_dists, triplets):
    exist_species = []
    tris = []
    tri_dir = []

    for m in range(bond_array.shape[0]):
        r1 = bond_array[m, 0]
        c1 = bond_array[m, 1:]
        spc1 = etypes[m]

        for n in range(triplets[m]):
            ind1 = cross_bond_inds[m, m+n+1]
            r2 = bond_array[ind1, 0]
            c2 = bond_array[ind1, 1:]
            spc2 = etypes[ind1]

            c12 = np.sum(c1*c2)
            r12 = np.sqrt(r1**2 + r2**2 - 2*r1*r2*c12)

#            triplet1 = array([r1, r2, r12])
#            triplet2 = array([r2, r1, r12])
#
#            if spc1 <= spc2:
#                spcs = [ctype, spc1, spc2]
#            else:
#                spcs = [ctype, spc2, spc1]
#
#            triplet = [triplet1, triplet2]
#            coord = [c1, c2] 
#
#            if spcs not in exist_species:
#                exist_species.append(spcs)
#                tris += [triplet]
#                tri_dir += [coord]
#            else:
#                k = exist_species.index(spcs)
#                tris[k] += triplet
#                tri_dir[k] += coord

            spcs_list = [[ctype, spc1, spc2], [ctype, spc2, spc1]]
            for i in range(2):
                spcs = spcs_list[i]
                triplet = array([r2, r1, r12]) if i else array([r1, r2, r12])
                coord = c2 if i else c1 # TODO: figure out what's wrong. why not [c1, c2] for force map
                if spcs not in exist_species:
                    exist_species.append(spcs)
                    tris.append([triplet])
                    tri_dir.append([coord])
                else:
                    k = exist_species.index(spcs)
                    tris[k].append(triplet)
                    tri_dir[k].append(coord)

    return exist_species, tris, tri_dir
