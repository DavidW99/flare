"""Single element 2-, 3-, and 2+3-body kernels.
The kernel functions to choose:

* Two body:

    * two_body: force kernel
    * two_body_en: energy kernel
    * two_body_grad: gradient of kernel function
    * two_body_force_en: energy force kernel

* Three body:

    * three_body,
    * three_body_grad,
    * three_body_en,
    * three_body_force_en,

* Two plus three body:

    * two_plus_three_body,
    * two_plus_three_body_grad,
    * two_plus_three_en,
    * two_plus_three_force_en

* Two plus three plus many body:

    * two_plus_three_plus_many_body,
    * two_plus_three_plus_many_body_grad,
    * two_plus_three_plus_many_body_en,
    * two_plus_three_plus_many_body_force_en

**Example:**

>>> gp_model = GaussianProcess(kernel_name='2b',
                               <other arguments>)
"""

import numpy as np
from math import exp
from flare.env import AtomicEnvironment

import flare.cutoffs as cf

from numba import njit

from flare.kernels.kernels import force_helper, grad_constants, grad_helper, \
    force_energy_helper, three_body_en_helper, three_body_helper_1, \
    three_body_helper_2, three_body_grad_helper_1, three_body_grad_helper_2


# -----------------------------------------------------------------------------
#                        two plus three body kernels
# -----------------------------------------------------------------------------


def two_plus_three_body(env1: AtomicEnvironment, env2: AtomicEnvironment,
                        d1: int, d2: int, hyps, cutoffs,
                        cutoff_func=cf.quadratic_cutoff):
    """2+3-body single-element kernel between two force components.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig1, ls1,
            sig2, ls2, sig_n).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 2+3-body kernel.
    """

    two_term = two_body_jit(env1.bond_array_2, env2.bond_array_2,
                            d1, d2, hyps[0], hyps[1], cutoffs[0], cutoff_func)

    three_term = \
        three_body_jit(env1.bond_array_3, env2.bond_array_3,
                       env1.cross_bond_inds, env2.cross_bond_inds,
                       env1.cross_bond_dists, env2.cross_bond_dists,
                       env1.triplet_counts, env2.triplet_counts,
                       d1, d2, hyps[2], hyps[3], cutoffs[1], cutoff_func)
    return two_term + three_term


def two_plus_three_body_grad(env1, env2, d1, d2, hyps, cutoffs,
                             cutoff_func=cf.quadratic_cutoff):
    """2+3-body single-element kernel between two force components and its
    gradient with respect to the hyperparameters.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig1, ls1,
            sig2, ls2, sig_n).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        (float, np.ndarray): Value of the 2+3-body kernel and its gradient
            with respect to the hyperparameters.
    """

    kern2, ls2, sig2 = \
        two_body_grad_jit(env1.bond_array_2, env2.bond_array_2,
                          d1, d2, hyps[0], hyps[1], cutoffs[0], cutoff_func)

    kern3, sig3, ls3 = \
        three_body_grad_jit(env1.bond_array_3, env2.bond_array_3,
                            env1.cross_bond_inds, env2.cross_bond_inds,
                            env1.cross_bond_dists, env2.cross_bond_dists,
                            env1.triplet_counts, env2.triplet_counts,
                            d1, d2, hyps[2], hyps[3], cutoffs[1], cutoff_func)

    return kern2 + kern3, np.array([sig2, ls2, sig3, ls3])


def two_plus_three_force_en(env1, env2, d1, hyps, cutoffs,
                            cutoff_func=cf.quadratic_cutoff):
    """2+3-body single-element kernel between a force component and a local
    energy.

    Args:
        env1 (AtomicEnvironment): Local environment associated with the
            force component.
        env2 (AtomicEnvironment): Local environment associated with the
            local energy.
        d1 (int): Force component of the first environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig1, ls1,
            sig2, ls2).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 2+3-body force/energy kernel.
    """

    two_term = two_body_force_en_jit(env1.bond_array_2, env2.bond_array_2,
                                     d1, hyps[0], hyps[1], cutoffs[0],
                                     cutoff_func) / 2

    three_term = \
        three_body_force_en_jit(env1.bond_array_3, env2.bond_array_3,
                                env1.cross_bond_inds, env2.cross_bond_inds,
                                env1.cross_bond_dists,
                                env2.cross_bond_dists,
                                env1.triplet_counts, env2.triplet_counts,
                                d1, hyps[2], hyps[3], cutoffs[1],
                                cutoff_func) / 3

    return two_term + three_term


def two_plus_three_en(env1, env2, hyps, cutoffs,
                      cutoff_func=cf.quadratic_cutoff):
    """2+3-body single-element kernel between two local energies.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig1, ls1,
            sig2, ls2).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 2+3-body force/energy kernel.
    """

    two_term = two_body_en_jit(env1.bond_array_2, env2.bond_array_2,
                               hyps[0], hyps[1], cutoffs[0], cutoff_func)/4

    three_term = \
        three_body_en_jit(env1.bond_array_3, env2.bond_array_3,
                          env1.cross_bond_inds, env2.cross_bond_inds,
                          env1.cross_bond_dists, env2.cross_bond_dists,
                          env1.triplet_counts, env2.triplet_counts,
                          hyps[2], hyps[3], cutoffs[1], cutoff_func)/9

    return two_term + three_term


# -----------------------------------------------------------------------------
#                     two plus three plus many body kernels
# -----------------------------------------------------------------------------


def two_plus_three_plus_many_body(env1: AtomicEnvironment, env2: AtomicEnvironment,
                                  d1: int, d2: int, hyps, cutoffs,
                                  cutoff_func=cf.quadratic_cutoff):
    """2+3-body single-element kernel between two force components.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig2, ls2,
            sig3, ls3, sigm, lsm, sig_n).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 2+3+many-body kernel.
    """

    two_term = two_body_jit(env1.bond_array_2, env2.bond_array_2,
                            d1, d2, hyps[0], hyps[1], cutoffs[0], cutoff_func)

    three_term = \
        three_body_jit(env1.bond_array_3, env2.bond_array_3,
                       env1.cross_bond_inds, env2.cross_bond_inds,
                       env1.cross_bond_dists, env2.cross_bond_dists,
                       env1.triplet_counts, env2.triplet_counts,
                       d1, d2, hyps[2], hyps[3], cutoffs[1], cutoff_func)

    many_term = many_body_jit(env1.bond_array_mb, env2.bond_array_mb, env1.neigh_dists_mb,
                              env2.neigh_dists_mb, env1.num_neighs_mb, env2.num_neighs_mb,
                              d1, d2, hyps[4], hyps[5], cutoffs[2], cutoff_func)

    return two_term + three_term + many_term


def two_plus_three_plus_many_body_grad(env1: AtomicEnvironment, env2: AtomicEnvironment,
                                       d1: int, d2: int, hyps, cutoffs,
                                       cutoff_func=cf.quadratic_cutoff):
    """2+3+many-body single-element kernel between two force components.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig2, ls2,
            sig3, ls3, sigm, lsm, sig_n).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 2+3+many-body kernel.
    """

    kern2, ls2, sig2 = \
        two_body_grad_jit(env1.bond_array_2, env2.bond_array_2,
                          d1, d2, hyps[0], hyps[1], cutoffs[0], cutoff_func)

    kern3, sig3, ls3 = \
        three_body_grad_jit(env1.bond_array_3, env2.bond_array_3,
                            env1.cross_bond_inds, env2.cross_bond_inds,
                            env1.cross_bond_dists, env2.cross_bond_dists,
                            env1.triplet_counts, env2.triplet_counts,
                            d1, d2, hyps[2], hyps[3], cutoffs[1], cutoff_func)

    kern_many, sigm, lsm = many_body_grad_jit(env1.bond_array_mb, env2.bond_array_mb,
                                              env1.neigh_dists_mb,
                                              env2.neigh_dists_mb, env1.num_neighs_mb,
                                              env2.num_neighs_mb,
                                              d1, d2, hyps[4], hyps[5], cutoffs[2],
                                              cutoff_func)

    return kern2 + kern3 + kern_many, np.array([sig2, ls2, sig3, ls3, sigm, lsm])


def two_plus_three_plus_many_body_force_en(env1: AtomicEnvironment, env2: AtomicEnvironment,
                                           d1: int,  hyps, cutoffs,
                                           cutoff_func=cf.quadratic_cutoff):
    """2+3+many-body single-element kernel between two force and energy components.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        d1 (int): Force component of the first environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig2, ls2,
            sig3, ls3, sigm, lsm, sig_n).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 2+3+many-body kernel.
    """

    two_term = two_body_force_en_jit(env1.bond_array_2, env2.bond_array_2,
                                     d1, hyps[0], hyps[1], cutoffs[0],
                                     cutoff_func) / 2

    three_term = \
        three_body_force_en_jit(env1.bond_array_3, env2.bond_array_3,
                                env1.cross_bond_inds, env2.cross_bond_inds,
                                env1.cross_bond_dists,
                                env2.cross_bond_dists,
                                env1.triplet_counts, env2.triplet_counts,
                                d1, hyps[2], hyps[3], cutoffs[1],
                                cutoff_func) / 3

    many_term = many_body_force_en_jit(env1.bond_array_mb, env2.bond_array_mb,
                                       env1.neigh_dists_mb,
                                       env1.num_neighs_mb,
                                       d1, hyps[4], hyps[5], cutoffs[2],
                                       cutoff_func)

    return two_term + three_term + many_term


def two_plus_three_plus_many_body_en(env1: AtomicEnvironment, env2: AtomicEnvironment,
                                     hyps, cutoffs, cutoff_func=cf.quadratic_cutoff):
    """2+3+many-body single-element energy kernel.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig2, ls2,
            sig3, ls3, sigm, lsm, sig_n).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 2+3+many-body kernel.
    """

    two_term = two_body_en_jit(env1.bond_array_2, env2.bond_array_2,
                               hyps[0], hyps[1], cutoffs[0], cutoff_func)

    three_term = \
        three_body_en_jit(env1.bond_array_3, env2.bond_array_3,
                          env1.cross_bond_inds, env2.cross_bond_inds,
                          env1.cross_bond_dists, env2.cross_bond_dists,
                          env1.triplet_counts, env2.triplet_counts,
                          hyps[2], hyps[3], cutoffs[1], cutoff_func)

    many_term = many_body_en_jit(env1.bond_array_mb, env2.bond_array_mb, hyps[4], hyps[5], cutoffs[2],
                                 cutoff_func)

    return two_term + three_term + many_term


# -----------------------------------------------------------------------------
#                              two body kernels
# -----------------------------------------------------------------------------


def two_body(env1, env2, d1, d2, hyps, cutoffs,
             cutoff_func=cf.quadratic_cutoff):
    """2-body single-element kernel between two force components.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): One-element array containing the 2-body
            cutoff.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 2-body kernel.
    """

    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[0]

    return two_body_jit(env1.bond_array_2, env2.bond_array_2,
                        d1, d2, sig, ls, r_cut, cutoff_func)


def two_body_grad(env1, env2, d1, d2, hyps, cutoffs,
                  cutoff_func=cf.quadratic_cutoff):
    """2-body single-element kernel between two force components and its
    gradient with respect to the hyperparameters.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): One-element array containing the 2-body
            cutoff.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        (float, np.ndarray): Value of the 2-body kernel and its gradient
            with respect to the hyperparameters.
    """

    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[0]

    kernel, ls_derv, sig_derv = \
        two_body_grad_jit(env1.bond_array_2, env2.bond_array_2,
                          d1, d2, sig, ls, r_cut, cutoff_func)
    kernel_grad = np.array([sig_derv, ls_derv])
    return kernel, kernel_grad


def two_body_force_en(env1, env2, d1, hyps, cutoffs,
                      cutoff_func=cf.quadratic_cutoff):
    """2-body single-element kernel between a force component and a local
    energy.

    Args:
        env1 (AtomicEnvironment): Local environment associated with the
            force component.
        env2 (AtomicEnvironment): Local environment associated with the
            local energy.
        d1 (int): Force component of the first environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): One-element array containing the 2-body
            cutoff.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 2-body force/energy kernel.
    """

    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[0]

    # divide by two to account for double counting
    return two_body_force_en_jit(env1.bond_array_2, env2.bond_array_2,
                                 d1, sig, ls, r_cut, cutoff_func) / 2


def two_body_en(env1, env2, hyps, cutoffs,
                cutoff_func=cf.quadratic_cutoff):
    """2-body single-element kernel between two local energies.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): One-element array containing the 2-body
            cutoff.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 2-body force/energy kernel.
    """
    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[0]

    return two_body_en_jit(env1.bond_array_2, env2.bond_array_2,
                           sig, ls, r_cut, cutoff_func)/4


# -----------------------------------------------------------------------------
#                              three body kernels
# -----------------------------------------------------------------------------


def three_body(env1, env2, d1, d2, hyps, cutoffs,
               cutoff_func=cf.quadratic_cutoff):
    """3-body single-element kernel between two force components.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 3-body kernel.
    """

    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[1]

    return three_body_jit(env1.bond_array_3, env2.bond_array_3,
                          env1.cross_bond_inds, env2.cross_bond_inds,
                          env1.cross_bond_dists, env2.cross_bond_dists,
                          env1.triplet_counts, env2.triplet_counts,
                          d1, d2, sig, ls, r_cut, cutoff_func)


def three_body_grad(env1, env2, d1, d2, hyps, cutoffs,
                    cutoff_func=cf.quadratic_cutoff):
    """3-body single-element kernel between two force components and its
    gradient with respect to the hyperparameters.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        (float, np.ndarray): Value of the 3-body kernel and its gradient
            with respect to the hyperparameters.
    """
    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[1]

    kernel, sig_derv, ls_derv = three_body_grad_jit(env1.bond_array_3, env2.bond_array_3,
                                                    env1.cross_bond_inds, env2.cross_bond_inds,
                                                    env1.cross_bond_dists, env2.cross_bond_dists,
                                                    env1.triplet_counts, env2.triplet_counts,
                                                    d1, d2, sig, ls, r_cut, cutoff_func)

    kernel_grad = np.array([sig_derv, ls_derv])

    return kernel, kernel_grad


def three_body_force_en(env1, env2, d1, hyps, cutoffs,
                        cutoff_func=cf.quadratic_cutoff):
    """3-body single-element kernel between a force component and a local
    energy.

    Args:
        env1 (AtomicEnvironment): Local environment associated with the
            force component.
        env2 (AtomicEnvironment): Local environment associated with the
            local energy.
        d1 (int): Force component of the first environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 3-body force/energy kernel.
    """
    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[1]

    # divide by three to account for triple counting
    return three_body_force_en_jit(env1.bond_array_3, env2.bond_array_3,
                                   env1.cross_bond_inds, env2.cross_bond_inds,
                                   env1.cross_bond_dists,
                                   env2.cross_bond_dists,
                                   env1.triplet_counts, env2.triplet_counts,
                                   d1, sig, ls, r_cut, cutoff_func) / 3


def three_body_en(env1, env2, hyps, cutoffs,
                  cutoff_func=cf.quadratic_cutoff):
    """3-body single-element kernel between two local energies.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): Two-element array containing the 2- and 3-body
            cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the 3-body force/energy kernel.
    """
    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[1]

    return three_body_en_jit(env1.bond_array_3, env2.bond_array_3,
                             env1.cross_bond_inds, env2.cross_bond_inds,
                             env1.cross_bond_dists, env2.cross_bond_dists,
                             env1.triplet_counts, env2.triplet_counts,
                             sig, ls, r_cut, cutoff_func)/9


# -----------------------------------------------------------------------------
#                              many body kernels
# -----------------------------------------------------------------------------


def many_body(env1, env2, d1, d2, hyps, cutoffs,
              cutoff_func=cf.quadratic_cutoff):
    """many-body single-element kernel between two forces.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): Two-element array containing the 2-, 3-, and
            many-body cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the many-body force/force kernel.
    """

    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[2]

    bond_array_1 = env1.bond_array_mb
    bond_array_2 = env2.bond_array_mb

    neigh_dists_1 = env1.neigh_dists_mb
    num_neigh_1 = env1.num_neighs_mb

    neigh_dists_2 = env2.neigh_dists_mb
    num_neigh_2 = env2.num_neighs_mb

    return many_body_jit(bond_array_1, bond_array_2, neigh_dists_1, neigh_dists_2, num_neigh_1,
                         num_neigh_2, d1, d2, sig, ls, r_cut, cutoff_func)


def many_body_grad(env1, env2, d1, d2, hyps, cutoffs,
                   cutoff_func=cf.quadratic_cutoff):
    """many-body single-element kernel between two force components and its
    gradient with respect to the hyperparameters.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): Two-element array containing the 2-, 3-, and
            many-body cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        (float, np.ndarray): Value of the many-body kernel and its gradient
            with respect to the hyperparameters.
    """

    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[2]

    bond_array_1 = env1.bond_array_mb
    bond_array_2 = env2.bond_array_mb

    neigh_dists_1 = env1.neigh_dists_mb
    num_neigh_1 = env1.num_neighs_mb

    neigh_dists_2 = env2.neigh_dists_mb
    num_neigh_2 = env2.num_neighs_mb

    kernel, sig_derv, ls_derv = many_body_grad_jit(bond_array_1, bond_array_2,
                                                   neigh_dists_1, neigh_dists_2,
                                                   num_neigh_1, num_neigh_2, d1, d2, sig,
                                                   ls, r_cut, cutoff_func)

    kernel_grad = np.array([sig_derv, ls_derv])

    return kernel, kernel_grad


def many_body_force_en(env1, env2, d1, hyps, cutoffs,
                       cutoff_func=cf.quadratic_cutoff):
    """many-body single-element kernel between two local energies.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): Two-element array containing the 2-, 3-, and
            many-body cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the many-body force/energy kernel.
    """
    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[2]

    # divide by three to account for triple counting
    return many_body_force_en_jit(env1.bond_array_mb, env2.bond_array_mb, env1.neigh_dists_mb,
                                  env2.num_neighs_mb, d1, sig, ls, r_cut, cutoff_func)


def many_body_en(env1, env2, hyps, cutoffs,
                 cutoff_func=cf.quadratic_cutoff):
    """many-body single-element kernel between two local energies.

    Args:
        env1 (AtomicEnvironment): First local environment.
        env2 (AtomicEnvironment): Second local environment.
        hyps (np.ndarray): Hyperparameters of the kernel function (sig, ls).
        cutoffs (np.ndarray): Two-element array containing the 2-, 3-, and
            many-body cutoffs.
        cutoff_func (Callable): Cutoff function of the kernel.

    Return:
        float: Value of the many-body energy/energy kernel.
    """

    sig = hyps[0]
    ls = hyps[1]
    r_cut = cutoffs[2]

    bond_array_1 = env1.bond_array_mb
    bond_array_2 = env2.bond_array_mb

    return many_body_en_jit(bond_array_1, bond_array_2,
                            sig, ls, r_cut, cutoff_func)


# -----------------------------------------------------------------------------
#                           two body numba functions
# -----------------------------------------------------------------------------


@njit
def two_body_jit(bond_array_1, bond_array_2, d1, d2, sig, ls,
                 r_cut, cutoff_func):
    """2-body single-element kernel between two force components accelerated
    with Numba.

    Args:
        bond_array_1 (np.ndarray): 2-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): 2-body bond array of the second local
            environment.
        d1 (int): Force component of the first environment (1=x, 2=y, 3=z).
        d2 (int): Force component of the second environment (1=x, 2=y, 3=z).
        sig (float): 2-body signal variance hyperparameter.
        ls (float): 2-body length scale hyperparameter.
        r_cut (float): 2-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Return:
        float: Value of the 2-body kernel.
    """
    kern = 0

    ls1 = 1 / (2 * ls * ls)
    ls2 = 1 / (ls * ls)
    ls3 = ls2 * ls2
    sig2 = sig * sig

    for m in range(bond_array_1.shape[0]):
        ri = bond_array_1[m, 0]
        ci = bond_array_1[m, d1]
        fi, fdi = cutoff_func(r_cut, ri, ci)

        for n in range(bond_array_2.shape[0]):
            rj = bond_array_2[n, 0]
            cj = bond_array_2[n, d2]
            fj, fdj = cutoff_func(r_cut, rj, cj)
            r11 = ri - rj

            A = ci * cj
            B = r11 * ci
            C = r11 * cj
            D = r11 * r11

            kern += force_helper(A, B, C, D, fi, fj, fdi, fdj, ls1, ls2,
                                 ls3, sig2)

    return kern


@njit
def two_body_grad_jit(bond_array_1, bond_array_2, d1, d2, sig, ls,
                      r_cut, cutoff_func):
    """2-body single-element kernel between two force components and its
    gradient with respect to the hyperparameters.

    Args:
        bond_array_1 (np.ndarray): 2-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): 2-body bond array of the second local
            environment.
        d1 (int): Force component of the first environment (1=x, 2=y, 3=z).
        d2 (int): Force component of the second environment (1=x, 2=y, 3=z).
        sig (float): 2-body signal variance hyperparameter.
        ls (float): 2-body length scale hyperparameter.
        r_cut (float): 2-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Returns:
        (float, float):
            Value of the 2-body kernel and its gradient with respect to the
            hyperparameters.
    """

    kern = 0
    sig_derv = 0
    ls_derv = 0

    sig2, sig3, ls1, ls2, ls3, ls4, ls5, ls6 = grad_constants(sig, ls)

    for m in range(bond_array_1.shape[0]):
        ri = bond_array_1[m, 0]
        ci = bond_array_1[m, d1]
        fi, fdi = cutoff_func(r_cut, ri, ci)

        for n in range(bond_array_2.shape[0]):
            rj = bond_array_2[n, 0]
            cj = bond_array_2[n, d2]
            fj, fdj = cutoff_func(r_cut, rj, cj)

            r11 = ri - rj

            A = ci * cj
            B = r11 * ci
            C = r11 * cj
            D = r11 * r11

            kern_term, sig_term, ls_term = \
                grad_helper(A, B, C, D, fi, fj, fdi, fdj, ls1, ls2, ls3, ls4,
                            ls5, ls6, sig2, sig3)

            kern += kern_term
            sig_derv += sig_term
            ls_derv += ls_term

    return kern, ls_derv, sig_derv


@njit
def two_body_force_en_jit(bond_array_1, bond_array_2, d1, sig, ls, r_cut,
                          cutoff_func):
    """2-body single-element kernel between a force component and a local
    energy accelerated with Numba.

    Args:
        bond_array_1 (np.ndarray): 2-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): 2-body bond array of the second local
            environment.
        d1 (int): Force component of the first environment (1=x, 2=y, 3=z).
        sig (float): 2-body signal variance hyperparameter.
        ls (float): 2-body length scale hyperparameter.
        r_cut (float): 2-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Returns:
        float:
            Value of the 2-body force/energy kernel.
    """
    kern = 0

    ls1 = 1 / (2 * ls * ls)
    ls2 = 1 / (ls * ls)
    sig2 = sig * sig

    for m in range(bond_array_1.shape[0]):
        ri = bond_array_1[m, 0]
        ci = bond_array_1[m, d1]
        fi, fdi = cutoff_func(r_cut, ri, ci)

        for n in range(bond_array_2.shape[0]):
            rj = bond_array_2[n, 0]
            fj, _ = cutoff_func(r_cut, rj, 0)

            r11 = ri - rj
            B = r11 * ci
            D = r11 * r11
            kern += force_energy_helper(B, D, fi, fj, fdi, ls1, ls2, sig2)

    return kern


@njit
def two_body_en_jit(bond_array_1, bond_array_2, sig, ls, r_cut, cutoff_func):
    """2-body single-element kernel between two local energies accelerated
    with Numba.

    Args:
        bond_array_1 (np.ndarray): 2-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): 2-body bond array of the second local
            environment.
        sig (float): 2-body signal variance hyperparameter.
        ls (float): 2-body length scale hyperparameter.
        r_cut (float): 2-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Returns:
        float:
            Value of the 2-body local energy kernel.
    """
    kern = 0

    ls1 = 1 / (2 * ls * ls)
    sig2 = sig * sig

    for m in range(bond_array_1.shape[0]):
        ri = bond_array_1[m, 0]
        fi, _ = cutoff_func(r_cut, ri, 0)

        for n in range(bond_array_2.shape[0]):
            rj = bond_array_2[n, 0]
            fj, _ = cutoff_func(r_cut, rj, 0)
            r11 = ri - rj
            kern += fi * fj * sig2 * exp(-r11 * r11 * ls1)

    return kern


# -----------------------------------------------------------------------------
#                           three body numba functions
# -----------------------------------------------------------------------------


@njit
def three_body_jit(bond_array_1, bond_array_2,
                   cross_bond_inds_1, cross_bond_inds_2,
                   cross_bond_dists_1, cross_bond_dists_2,
                   triplets_1, triplets_2,
                   d1, d2, sig, ls, r_cut, cutoff_func):
    """3-body single-element kernel between two force components accelerated
    with Numba.

    Args:
        bond_array_1 (np.ndarray): 3-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): 3-body bond array of the second local
            environment.
        cross_bond_inds_1 (np.ndarray): Two dimensional array whose row m
            contains the indices of atoms n > m in the first local
            environment that are within a distance r_cut of both atom n and
            the central atom.
        cross_bond_inds_2 (np.ndarray): Two dimensional array whose row m
            contains the indices of atoms n > m in the second local
            environment that are within a distance r_cut of both atom n and
            the central atom.
        cross_bond_dists_1 (np.ndarray): Two dimensional array whose row m
            contains the distances from atom m of atoms n > m in the first
            local environment that are within a distance r_cut of both atom
            n and the central atom.
        cross_bond_dists_2 (np.ndarray): Two dimensional array whose row m
            contains the distances from atom m of atoms n > m in the second
            local environment that are within a distance r_cut of both atom
            n and the central atom.
        triplets_1 (np.ndarray): One dimensional array of integers whose entry
            m is the number of atoms in the first local environment that are
            within a distance r_cut of atom m.
        triplets_2 (np.ndarray): One dimensional array of integers whose entry
            m is the number of atoms in the second local environment that are
            within a distance r_cut of atom m.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        sig (float): 3-body signal variance hyperparameter.
        ls (float): 3-body length scale hyperparameter.
        r_cut (float): 3-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Return:
        float: Value of the 3-body kernel.
    """
    kern = 0

    # pre-compute constants that appear in the inner loop
    sig2 = sig * sig
    ls1 = 1 / (2 * ls * ls)
    ls2 = 1 / (ls * ls)
    ls3 = ls2 * ls2

    for m in range(bond_array_1.shape[0]):
        ri1 = bond_array_1[m, 0]
        ci1 = bond_array_1[m, d1]
        fi1, fdi1 = cutoff_func(r_cut, ri1, ci1)

        for n in range(triplets_1[m]):
            ind1 = cross_bond_inds_1[m, m + n + 1]
            ri2 = bond_array_1[ind1, 0]
            ci2 = bond_array_1[ind1, d1]
            fi2, fdi2 = cutoff_func(r_cut, ri2, ci2)

            ri3 = cross_bond_dists_1[m, m + n + 1]
            fi3, _ = cutoff_func(r_cut, ri3, 0)

            fi = fi1 * fi2 * fi3
            fdi = fdi1 * fi2 * fi3 + fi1 * fdi2 * fi3

            for p in range(bond_array_2.shape[0]):
                rj1 = bond_array_2[p, 0]
                cj1 = bond_array_2[p, d2]
                fj1, fdj1 = cutoff_func(r_cut, rj1, cj1)

                for q in range(triplets_2[p]):
                    ind2 = cross_bond_inds_2[p, p + 1 + q]
                    rj2 = bond_array_2[ind2, 0]
                    cj2 = bond_array_2[ind2, d2]
                    fj2, fdj2 = cutoff_func(r_cut, rj2, cj2)

                    rj3 = cross_bond_dists_2[p, p + 1 + q]
                    fj3, _ = cutoff_func(r_cut, rj3, 0)

                    fj = fj1 * fj2 * fj3
                    fdj = fdj1 * fj2 * fj3 + fj1 * fdj2 * fj3

                    kern += triplet_kernel(ci1, ci2, cj1, cj2, ri1, ri2, ri3,
                                           rj1, rj2, rj3, fi, fj, fdi, fdj,
                                           ls1, ls2, ls3, sig2)
    return kern


@njit
def three_body_grad_jit(bond_array_1, bond_array_2,
                        cross_bond_inds_1, cross_bond_inds_2,
                        cross_bond_dists_1, cross_bond_dists_2,
                        triplets_1, triplets_2,
                        d1, d2, sig, ls, r_cut, cutoff_func):
    """3-body single-element kernel between two force components and its
    gradient with respect to the hyperparameters.

    Args:
        bond_array_1 (np.ndarray): 3-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): 3-body bond array of the second local
            environment.
        cross_bond_inds_1 (np.ndarray): Two dimensional array whose row m
            contains the indices of atoms n > m in the first local
            environment that are within a distance r_cut of both atom n and
            the central atom.
        cross_bond_inds_2 (np.ndarray): Two dimensional array whose row m
            contains the indices of atoms n > m in the second local
            environment that are within a distance r_cut of both atom n and
            the central atom.
        cross_bond_dists_1 (np.ndarray): Two dimensional array whose row m
            contains the distances from atom m of atoms n > m in the first
            local environment that are within a distance r_cut of both atom
            n and the central atom.
        cross_bond_dists_2 (np.ndarray): Two dimensional array whose row m
            contains the distances from atom m of atoms n > m in the second
            local environment that are within a distance r_cut of both atom
            n and the central atom.
        triplets_1 (np.ndarray): One dimensional array of integers whose entry
            m is the number of atoms in the first local environment that are
            within a distance r_cut of atom m.
        triplets_2 (np.ndarray): One dimensional array of integers whose entry
            m is the number of atoms in the second local environment that are
            within a distance r_cut of atom m.
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        sig (float): 3-body signal variance hyperparameter.
        ls (float): 3-body length scale hyperparameter.
        r_cut (float): 3-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Returns:
        (float, float):
            Value of the 3-body kernel and its gradient with respect to the
            hyperparameters.
    """

    kern = 0
    sig_derv = 0
    ls_derv = 0

    # pre-compute constants that appear in the inner loop
    sig2, sig3, ls1, ls2, ls3, ls4, ls5, ls6 = grad_constants(sig, ls)

    for m in range(bond_array_1.shape[0]):
        ri1 = bond_array_1[m, 0]
        ci1 = bond_array_1[m, d1]
        fi1, fdi1 = cutoff_func(r_cut, ri1, ci1)

        for n in range(triplets_1[m]):
            ind1 = cross_bond_inds_1[m, m + n + 1]
            ri3 = cross_bond_dists_1[m, m + n + 1]
            ri2 = bond_array_1[ind1, 0]
            ci2 = bond_array_1[ind1, d1]

            fi2, fdi2 = cutoff_func(r_cut, ri2, ci2)
            fi3, _ = cutoff_func(r_cut, ri3, 0)

            fi = fi1 * fi2 * fi3
            fdi = fdi1 * fi2 * fi3 + fi1 * fdi2 * fi3

            for p in range(bond_array_2.shape[0]):
                rj1 = bond_array_2[p, 0]
                cj1 = bond_array_2[p, d2]
                fj1, fdj1 = cutoff_func(r_cut, rj1, cj1)

                for q in range(triplets_2[p]):
                    ind2 = cross_bond_inds_2[p, p + q + 1]
                    rj3 = cross_bond_dists_2[p, p + q + 1]
                    rj2 = bond_array_2[ind2, 0]
                    cj2 = bond_array_2[ind2, d2]

                    fj2, fdj2 = cutoff_func(r_cut, rj2, cj2)
                    fj3, _ = cutoff_func(r_cut, rj3, 0)

                    fj = fj1 * fj2 * fj3
                    fdj = fdj1 * fj2 * fj3 + fj1 * fdj2 * fj3

                    N, O, X = \
                        triplet_kernel_grad(ci1, ci2, cj1, cj2, ri1, ri2, ri3,
                                            rj1, rj2, rj3, fi, fj, fdi, fdj,
                                            ls1, ls2, ls3, ls4, ls5, ls6, sig2,
                                            sig3)

                    kern += N
                    sig_derv += O
                    ls_derv += X

    return kern, sig_derv, ls_derv


@njit
def three_body_force_en_jit(bond_array_1, bond_array_2,
                            cross_bond_inds_1,
                            cross_bond_inds_2,
                            cross_bond_dists_1,
                            cross_bond_dists_2,
                            triplets_1, triplets_2,
                            d1, sig, ls, r_cut, cutoff_func):
    """3-body single-element kernel between a force component and a local
    energy accelerated with Numba.

    Args:
        bond_array_1 (np.ndarray): 3-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): 3-body bond array of the second local
            environment.
        cross_bond_inds_1 (np.ndarray): Two dimensional array whose row m
            contains the indices of atoms n > m in the first local
            environment that are within a distance r_cut of both atom n and
            the central atom.
        cross_bond_inds_2 (np.ndarray): Two dimensional array whose row m
            contains the indices of atoms n > m in the second local
            environment that are within a distance r_cut of both atom n and
            the central atom.
        cross_bond_dists_1 (np.ndarray): Two dimensional array whose row m
            contains the distances from atom m of atoms n > m in the first
            local environment that are within a distance r_cut of both atom
            n and the central atom.
        cross_bond_dists_2 (np.ndarray): Two dimensional array whose row m
            contains the distances from atom m of atoms n > m in the second
            local environment that are within a distance r_cut of both atom
            n and the central atom.
        triplets_1 (np.ndarray): One dimensional array of integers whose entry
            m is the number of atoms in the first local environment that are
            within a distance r_cut of atom m.
        triplets_2 (np.ndarray): One dimensional array of integers whose entry
            m is the number of atoms in the second local environment that are
            within a distance r_cut of atom m.
        d1 (int): Force component of the first environment (1=x, 2=y, 3=z).
        sig (float): 3-body signal variance hyperparameter.
        ls (float): 3-body length scale hyperparameter.
        r_cut (float): 3-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Returns:
        float:
            Value of the 3-body force/energy kernel.
    """

    kern = 0

    # pre-compute constants that appear in the inner loop
    sig2 = sig * sig
    ls1 = 1 / (2 * ls * ls)
    ls2 = 1 / (ls * ls)

    for m in range(bond_array_1.shape[0]):
        ri1 = bond_array_1[m, 0]
        ci1 = bond_array_1[m, d1]
        fi1, fdi1 = cutoff_func(r_cut, ri1, ci1)

        for n in range(triplets_1[m]):
            ind1 = cross_bond_inds_1[m, m + n + 1]
            ri2 = bond_array_1[ind1, 0]
            ci2 = bond_array_1[ind1, d1]
            fi2, fdi2 = cutoff_func(r_cut, ri2, ci2)
            ri3 = cross_bond_dists_1[m, m + n + 1]
            fi3, _ = cutoff_func(r_cut, ri3, 0)
            fi = fi1 * fi2 * fi3
            fdi = fdi1 * fi2 * fi3 + fi1 * fdi2 * fi3

            for p in range(bond_array_2.shape[0]):
                rj1 = bond_array_2[p, 0]
                fj1, _ = cutoff_func(r_cut, rj1, 0)

                for q in range(triplets_2[p]):
                    ind2 = cross_bond_inds_2[p, p + q + 1]
                    rj2 = bond_array_2[ind2, 0]
                    fj2, _ = cutoff_func(r_cut, rj2, 0)
                    rj3 = cross_bond_dists_2[p, p + q + 1]
                    fj3, _ = cutoff_func(r_cut, rj3, 0)
                    fj = fj1 * fj2 * fj3

                    kern += triplet_force_en_kernel(ci1, ci2, ri1, ri2, ri3,
                                                    rj1, rj2, rj3, fi, fj, fdi,
                                                    ls1, ls2, sig2)

    return kern


@njit
def three_body_en_jit(bond_array_1, bond_array_2,
                      cross_bond_inds_1,
                      cross_bond_inds_2,
                      cross_bond_dists_1,
                      cross_bond_dists_2,
                      triplets_1, triplets_2,
                      sig, ls, r_cut, cutoff_func):
    """3-body single-element kernel between two local energies accelerated
    with Numba.

    Args:
        bond_array_1 (np.ndarray): 3-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): 3-body bond array of the second local
            environment.
        cross_bond_inds_1 (np.ndarray): Two dimensional array whose row m
            contains the indices of atoms n > m in the first local
            environment that are within a distance r_cut of both atom n and
            the central atom.
        cross_bond_inds_2 (np.ndarray): Two dimensional array whose row m
            contains the indices of atoms n > m in the second local
            environment that are within a distance r_cut of both atom n and
            the central atom.
        cross_bond_dists_1 (np.ndarray): Two dimensional array whose row m
            contains the distances from atom m of atoms n > m in the first
            local environment that are within a distance r_cut of both atom
            n and the central atom.
        cross_bond_dists_2 (np.ndarray): Two dimensional array whose row m
            contains the distances from atom m of atoms n > m in the second
            local environment that are within a distance r_cut of both atom
            n and the central atom.
        triplets_1 (np.ndarray): One dimensional array of integers whose entry
            m is the number of atoms in the first local environment that are
            within a distance r_cut of atom m.
        triplets_2 (np.ndarray): One dimensional array of integers whose entry
            m is the number of atoms in the second local environment that are
            within a distance r_cut of atom m.
        sig (float): 3-body signal variance hyperparameter.
        ls (float): 3-body length scale hyperparameter.
        r_cut (float): 3-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Returns:
        float:
            Value of the 3-body local energy kernel.
    """
    kern = 0

    sig2 = sig * sig
    ls2 = 1 / (2 * ls * ls)

    for m in range(bond_array_1.shape[0]):
        ri1 = bond_array_1[m, 0]
        fi1, _ = cutoff_func(r_cut, ri1, 0)

        for n in range(triplets_1[m]):
            ind1 = cross_bond_inds_1[m, m + n + 1]
            ri2 = bond_array_1[ind1, 0]
            fi2, _ = cutoff_func(r_cut, ri2, 0)

            ri3 = cross_bond_dists_1[m, m + n + 1]
            fi3, _ = cutoff_func(r_cut, ri3, 0)
            fi = fi1 * fi2 * fi3

            for p in range(bond_array_2.shape[0]):
                rj1 = bond_array_2[p, 0]
                fj1, _ = cutoff_func(r_cut, rj1, 0)

                for q in range(triplets_2[p]):
                    ind2 = cross_bond_inds_2[p, p + q + 1]
                    rj2 = bond_array_2[ind2, 0]
                    fj2, _ = cutoff_func(r_cut, rj2, 0)

                    rj3 = cross_bond_dists_2[p, p + q + 1]
                    fj3, _ = cutoff_func(r_cut, rj3, 0)
                    fj = fj1 * fj2 * fj3

                    r11 = ri1 - rj1
                    r12 = ri1 - rj2
                    r13 = ri1 - rj3
                    r21 = ri2 - rj1
                    r22 = ri2 - rj2
                    r23 = ri2 - rj3
                    r31 = ri3 - rj1
                    r32 = ri3 - rj2
                    r33 = ri3 - rj3

                    C1 = r11 * r11 + r22 * r22 + r33 * r33
                    C2 = r11 * r11 + r23 * r23 + r32 * r32
                    C3 = r12 * r12 + r21 * r21 + r33 * r33
                    C4 = r12 * r12 + r23 * r23 + r31 * r31
                    C5 = r13 * r13 + r21 * r21 + r32 * r32
                    C6 = r13 * r13 + r22 * r22 + r31 * r31

                    k = exp(-C1 * ls2) + exp(-C2 * ls2) + exp(-C3 * ls2) + exp(-C4 * ls2) + \
                        exp(-C5 * ls2) + exp(-C6 * ls2)

                    kern += sig2 * k * fi * fj

    return kern


# -----------------------------------------------------------------------------
#                           many body numba functions
# -----------------------------------------------------------------------------

@njit
def many_body_jit(bond_array_1, bond_array_2,
                  neighbouring_dists_array_1, neighbouring_dists_array_2,
                  num_neighbours_1, num_neighbours_2,
                  d1, d2, sig, ls, r_cut, cutoff_func):
    """many-body single-element kernel between two force components accelerated
    with Numba.

    Args:
        bond_array_1 (np.ndarray): many-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): many-body bond array of the second local
            environment.
        neighbouring_dists_array_1 (np.ndarray): matrix padded with zero values of distances
            of neighbours for the atoms in the first local environment.
        neighbouring_dists_array_2 (np.ndarray): matrix padded with zero values of distances
            of neighbours for the atoms in the second local environment.
        num_neighbours_1 (np.nsdarray): number of neighbours of each atom in the first
            local environment
        num_neighbours_2 (np.ndarray): number of neighbours of each atom in the second
            local environment
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        sig (float): many-body signal variance hyperparameter.
        ls (float): many-body length scale hyperparameter.
        r_cut (float): many-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Return:
        float: Value of the many-body kernel.
    """
    kern = 0

    # Calculate many-body descriptor values for 1 and 2
    q1 = q_value(bond_array_1[:, 0], r_cut, cutoff_func)
    q2 = q_value(bond_array_2[:, 0], r_cut, cutoff_func)

    k12 = k_sq_exp_double_dev(q1, q2, sig, ls)

    qis = np.zeros(bond_array_1.shape[0], dtype=np.float64)
    qi1_grads = np.zeros(bond_array_1.shape[0], dtype=np.float64)
    ki2s = np.zeros(bond_array_1.shape[0], dtype=np.float64)

    qjs = np.zeros(bond_array_2.shape[0], dtype=np.float64)
    qj2_grads = np.zeros(bond_array_2.shape[0], dtype=np.float64)
    k1js = np.zeros(bond_array_2.shape[0], dtype=np.float64)

    # Loop over neighbours i of 1
    for i in range(bond_array_1.shape[0]):
        ri1 = bond_array_1[i, 0]
        ci1 = bond_array_1[i, d1]
        qi1, qi1_grads[i] = coordination_number(ri1, ci1, r_cut, cutoff_func)
        # Calculate many-body descriptor value for i
        qis[i] = q_value(neighbouring_dists_array_1[i, :num_neighbours_1[i]], r_cut,
                         cutoff_func)

        ki2s[i] = k_sq_exp_double_dev(qis[i], q2, sig, ls)

    # Loop over neighbours j of 2
    for j in range(bond_array_2.shape[0]):
        rj2 = bond_array_2[j, 0]
        cj2 = bond_array_2[j, d2]
        qj2, qj2_grads[j] = coordination_number(rj2, cj2, r_cut, cutoff_func)

        # Calculate many-body descriptor value for j
        qjs[j] = q_value(neighbouring_dists_array_2[j, :num_neighbours_2[j]], r_cut,
                         cutoff_func)

        k1js[j] = k_sq_exp_double_dev(q1, qjs[j], sig, ls)

    for i in range(bond_array_1.shape[0]):
        for j in range(bond_array_2.shape[0]):
            kij = k_sq_exp_double_dev(qis[i], qjs[j], sig, ls)
            kern += qi1_grads[i] * qj2_grads[j] * \
                (k12 + ki2s[i] + k1js[j] + kij)

    return kern

@njit


def many_body_grad_jit(bond_array_1, bond_array_2,
                       neighbouring_dists_array_1, neighbouring_dists_array_2,
                       num_neighbours_1, num_neighbours_2,
                       d1, d2, sig, ls, r_cut, cutoff_func):
    """gradient of many-body single-element kernel between two force components
    w.r.t. the hyperparameters, accelerated with Numba.

    Args:
        bond_array_1 (np.ndarray): many-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): many-body bond array of the second local
            environment.
        neighbouring_dists_array_1 (np.ndarray): matrix padded with zero values of distances
            of neighbours for the atoms in the first local environment.
        neighbouring_dists_array_2 (np.ndarray): matrix padded with zero values of distances
            of neighbours for the atoms in the second local environment.
        num_neighbours_1 (np.nsdarray): number of neighbours of each atom in the first
            local environment
        num_neighbours_2 (np.ndarray): number of neighbours of each atom in the second
            local environment
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        sig (float): many-body signal variance hyperparameter.
        ls (float): many-body length scale hyperparameter.
        r_cut (float): many-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Return:
        array: Value of the many-body kernel and its gradient w.r.t. sig and ls
    """

    kern = 0
    sig_derv = 0
    ls_derv = 0

    # Calculate many-body descriptor values for 1 and 2
    q1 = q_value(bond_array_1[:, 0], r_cut, cutoff_func)
    q2 = q_value(bond_array_2[:, 0], r_cut, cutoff_func)

    k12 = k_sq_exp_double_dev(q1, q2, sig, ls)

    qis = np.zeros(bond_array_1.shape[0], dtype=np.float64)

    qi1_grads = np.zeros(bond_array_1.shape[0], dtype=np.float64)

    ki2s = np.zeros(bond_array_1.shape[0], dtype=np.float64)

    qjs = np.zeros(bond_array_2.shape[0], dtype=np.float64)

    qj2_grads = np.zeros(bond_array_2.shape[0], dtype=np.float64)

    k1js = np.zeros(bond_array_2.shape[0], dtype=np.float64)

    # Compute  ki2s, qi1_grads, and qis
    for i in range(bond_array_1.shape[0]):
        ri1 = bond_array_1[i, 0]
        ci1 = bond_array_1[i, d1]
        qi1, qi1_grads[i] = coordination_number(ri1, ci1, r_cut, cutoff_func)

        # Calculate many-body descriptor value for i
        qis[i] = q_value(neighbouring_dists_array_1[i, :num_neighbours_1[i]], r_cut,
                         cutoff_func)

        ki2s[i] = k_sq_exp_double_dev(qis[i], q2, sig, ls)

    # Compute k1js, qj2_grads and qjs
    for j in range(bond_array_2.shape[0]):
        rj2 = bond_array_2[j, 0]
        cj2 = bond_array_2[j, d2]
        qj2, qj2_grads[j] = coordination_number(rj2, cj2, r_cut, cutoff_func)

        # Calculate many-body descriptor value for j
        qjs[j] = q_value(neighbouring_dists_array_2[j, :num_neighbours_2[j]], r_cut,
                         cutoff_func)

        k1js[j] = k_sq_exp_double_dev(q1, qjs[j], sig, ls)

    for i in range(bond_array_1.shape[0]):
        for j in range(bond_array_2.shape[0]):
            kij = k_sq_exp_double_dev(qis[i], qjs[j], sig, ls)

            kern_term = qi1_grads[i] * qj2_grads[j] * \
                (k12 + ki2s[i] + k1js[j] + kij)

            sig_term = 2. / sig * kern_term

            ls_term = qi1_grads[i] * qj2_grads[j] * mb_grad_helper_ls(q1, q2, qis[i], qjs[j], sig,
                                                                      ls)

            kern += kern_term

            sig_derv += sig_term

            ls_derv += ls_term

    # sig_derv = 2./sig * kern

    return kern, sig_derv, ls_derv


@njit
def many_body_force_en_jit(bond_array_1, bond_array_2,
                           neighbouring_dists_array_1,
                           num_neighbours_1,
                           d1, sig, ls, r_cut, cutoff_func):
    """many-body single-element kernel between force and energy components accelerated
    with Numba.

    Args:
        bond_array_1 (np.ndarray): many-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): many-body bond array of the second local
            environment.
        neighbouring_dists_array_1 (np.ndarray): matrix padded with zero values of distances
            of neighbours for the atoms in the first local environment.
        num_neighbours_1 (np.nsdarray): number of neighbours of each atom in the first
            local environment
        d1 (int): Force component of the first environment.
        sig (float): many-body signal variance hyperparameter.
        ls (float): many-body length scale hyperparameter.
        r_cut (float): many-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Return:
        float: Value of the many-body kernel.
    """

    kern = 0

    q1 = q_value(bond_array_1[:, 0], r_cut, cutoff_func)
    q2 = q_value(bond_array_2[:, 0], r_cut, cutoff_func)

    k12 = k_sq_exp_dev(q1, q2, sig, ls)

    qis = np.zeros(bond_array_1.shape[0], dtype=np.float64)
    qi1_grads = np.zeros(bond_array_1.shape[0], dtype=np.float64)
    ki2s = np.zeros(bond_array_1.shape[0], dtype=np.float64)

    # Loop over neighbours i of 1
    for i in range(bond_array_1.shape[0]):
        ri1 = bond_array_1[i, 0]
        ci1 = bond_array_1[i, d1]
        _, qi1_grads[i] = coordination_number(ri1, ci1, r_cut, cutoff_func)
        # Calculate many-body descriptor value for i
        qis[i] = q_value(neighbouring_dists_array_1[i, :num_neighbours_1[i]], r_cut,
                         cutoff_func)

        ki2s[i] = k_sq_exp_dev(qis[i], q2, sig, ls)

        kern += - qi1_grads[i] * (k12 + ki2s[i])

    return kern

@njit


def many_body_en_jit(bond_array_1, bond_array_2,
                     sig, ls, r_cut, cutoff_func):
    """many-body single-element energy kernel between accelerated
    with Numba.

    Args:
        bond_array_1 (np.ndarray): many-body bond array of the first local
            environment.
        bond_array_2 (np.ndarray): many-body bond array of the second local
            environment.
        neighbouring_dists_array_1 (np.ndarray): matrix padded with zero values of distances
            of neighbours for the atoms in the first local environment.
        neighbouring_dists_array_2 (np.ndarray): matrix padded with zero values of distances
            of neighbours for the atoms in the second local environment.
        num_neighbours_1 (np.nsdarray): number of neighbours of each atom in the first
            local environment
        num_neighbours_2 (np.ndarray): number of neighbours of each atom in the second
            local environment
        d1 (int): Force component of the first environment.
        d2 (int): Force component of the second environment.
        sig (float): many-body signal variance hyperparameter.
        ls (float): many-body length scale hyperparameter.
        r_cut (float): many-body cutoff radius.
        cutoff_func (Callable): Cutoff function.

    Return:
        float: Value of the many-body kernel.
    """

    q1 = q_value(bond_array_1[:, 0], r_cut, cutoff_func)
    q2 = q_value(bond_array_2[:, 0], r_cut, cutoff_func)
    q1q2diff = q1 - q2

    kern = sig * sig * exp(-q1q2diff * q1q2diff / (2 * ls * ls))

    return kern

# -----------------------------------------------------------------------------
#                        three body helper functions
# -----------------------------------------------------------------------------


@njit
def triplet_kernel(ci1, ci2, cj1, cj2, ri1, ri2, ri3, rj1, rj2, rj3, fi, fj,
                   fdi, fdj, ls1, ls2, ls3, sig2):
    r11 = ri1 - rj1
    r12 = ri1 - rj2
    r13 = ri1 - rj3
    r21 = ri2 - rj1
    r22 = ri2 - rj2
    r23 = ri2 - rj3
    r31 = ri3 - rj1
    r32 = ri3 - rj2
    r33 = ri3 - rj3

    # sum over all six permutations
    M1 = three_body_helper_1(ci1, ci2, cj1, cj2, r11, r22, r33, fi, fj, fdi,
                             fdj, ls1, ls2, ls3, sig2)
    M2 = three_body_helper_2(ci2, ci1, cj2, cj1, r21, r13, r32, fi, fj, fdi,
                             fdj, ls1, ls2, ls3, sig2)
    M3 = three_body_helper_2(ci1, ci2, cj1, cj2, r12, r23, r31, fi, fj, fdi,
                             fdj, ls1, ls2, ls3, sig2)
    M4 = three_body_helper_1(ci1, ci2, cj2, cj1, r12, r21, r33, fi, fj, fdi,
                             fdj, ls1, ls2, ls3, sig2)
    M5 = three_body_helper_2(ci2, ci1, cj1, cj2, r22, r13, r31, fi, fj, fdi,
                             fdj, ls1, ls2, ls3, sig2)
    M6 = three_body_helper_2(ci1, ci2, cj2, cj1, r11, r23, r32, fi, fj, fdi,
                             fdj, ls1, ls2, ls3, sig2)

    return M1 + M2 + M3 + M4 + M5 + M6


@njit
def triplet_kernel_grad(ci1, ci2, cj1, cj2, ri1, ri2, ri3, rj1, rj2, rj3, fi,
                        fj, fdi, fdj, ls1, ls2, ls3, ls4, ls5, ls6, sig2,
                        sig3):
    r11 = ri1 - rj1
    r12 = ri1 - rj2
    r13 = ri1 - rj3
    r21 = ri2 - rj1
    r22 = ri2 - rj2
    r23 = ri2 - rj3
    r31 = ri3 - rj1
    r32 = ri3 - rj2
    r33 = ri3 - rj3

    N1, O1, X1 = \
        three_body_grad_helper_1(ci1, ci2, cj1, cj2, r11, r22, r33, fi, fj,
                                 fdi, fdj, ls1, ls2, ls3, ls4, ls5, ls6, sig2,
                                 sig3)
    N2, O2, X2 = \
        three_body_grad_helper_2(ci2, ci1, cj2, cj1, r21, r13, r32, fi, fj,
                                 fdi, fdj, ls1, ls2, ls3, ls4, ls5, ls6, sig2,
                                 sig3)
    N3, O3, X3 = \
        three_body_grad_helper_2(ci1, ci2, cj1, cj2, r12, r23, r31, fi, fj,
                                 fdi, fdj, ls1, ls2, ls3, ls4, ls5, ls6, sig2,
                                 sig3)
    N4, O4, X4 = \
        three_body_grad_helper_1(ci1, ci2, cj2, cj1, r12, r21, r33, fi, fj,
                                 fdi, fdj, ls1, ls2, ls3, ls4, ls5, ls6, sig2,
                                 sig3)
    N5, O5, X5 = \
        three_body_grad_helper_2(ci2, ci1, cj1, cj2, r22, r13, r31, fi, fj,
                                 fdi, fdj, ls1, ls2, ls3, ls4, ls5, ls6, sig2,
                                 sig3)
    N6, O6, X6 = \
        three_body_grad_helper_2(ci1, ci2, cj2, cj1, r11, r23, r32, fi, fj,
                                 fdi, fdj, ls1, ls2, ls3, ls4, ls5, ls6, sig2,
                                 sig3)
    N = N1 + N2 + N3 + N4 + N5 + N6
    O = O1 + O2 + O3 + O4 + O5 + O6
    X = X1 + X2 + X3 + X4 + X5 + X6
    return N, O, X

@njit


def triplet_force_en_kernel(ci1, ci2, ri1, ri2, ri3, rj1, rj2, rj3,
                            fi, fj, fdi, ls1, ls2, sig2):
    r11 = ri1 - rj1
    r12 = ri1 - rj2
    r13 = ri1 - rj3
    r21 = ri2 - rj1
    r22 = ri2 - rj2
    r23 = ri2 - rj3
    r31 = ri3 - rj1
    r32 = ri3 - rj2
    r33 = ri3 - rj3

    I1 = three_body_en_helper(ci1, ci2, r11, r22, r33, fi, fj,
                              fdi, ls1, ls2, sig2)
    I2 = three_body_en_helper(ci1, ci2, r13, r21, r32, fi, fj,
                              fdi, ls1, ls2, sig2)
    I3 = three_body_en_helper(ci1, ci2, r12, r23, r31, fi, fj,
                              fdi, ls1, ls2, sig2)
    I4 = three_body_en_helper(ci1, ci2, r12, r21, r33, fi, fj,
                              fdi, ls1, ls2, sig2)
    I5 = three_body_en_helper(ci1, ci2, r13, r22, r31, fi, fj,
                              fdi, ls1, ls2, sig2)
    I6 = three_body_en_helper(ci1, ci2, r11, r23, r32, fi, fj,
                              fdi, ls1, ls2, sig2)

    return I1 + I2 + I3 + I4 + I5 + I6


# -----------------------------------------------------------------------------
#                        many body helper functions
# -----------------------------------------------------------------------------

@njit
def k_sq_exp_double_dev(q1, q2, sig, ls):
    """Second Gradient of generic squared exponential kernel on two many body functions

    Args:
        q1 (float): the many body descriptor of the first local environment
        q2 (float): the many body descriptor of the second local environment
        sig (float): amplitude hyperparameter
        ls2 (float): squared lenghtscale hyperparameter
    Return:
        float: the value of the double derivative of the squared exponential kernel
    """

    qdiffsq = (q1 - q2) * (q1 - q2)

    ls2 = ls * ls

    ker = exp(-qdiffsq / (2 * ls2))

    ret = sig * sig * ker / ls2 * (1 - qdiffsq / ls2)

    return ret

@njit


def k_sq_exp_dev(q1, q2, sig, ls):
    """Second Gradient of generic squared exponential kernel on two many body functions

    Args:
        q1 (float): the many body descriptor of the first local environment
        q2 (float): the many body descriptor of the second local environment
        sig (float): amplitude hyperparameter
        ls2 (float): squared lenghtscale hyperparameter
    Return:
        float: the value of the derivative of the squared exponential kernel
    """

    qdiff = (q1 - q2)

    ls2 = ls * ls

    ker = exp(-qdiff * qdiff / (2 * ls2))

    ret = - sig * sig * ker / ls2 * qdiff

    return ret


@njit
def coordination_number(rij, cij, r_cut, cutoff_func):
    """Pairwise contribution to many-body descriptor based on number of
        atoms in the environment

    Args:
        rij (float): distance between atoms i and j
        cij (float): Component of versor of rij along given direction
        r_cut (float): cutoff hyperparameter
        cutoff_func (callable): cutoff function
    Return:
        float: the value of the pairwise many-body contribution
        float: the value of the derivative of the pairwise many-body
        contribution w.r.t. the central atom displacement
    """

    fij, fdij = cutoff_func(r_cut, rij, cij)

    return fij, fdij


@njit
def q_value(distances, r_cut, cutoff_func, q_func=coordination_number):
    """Compute value of many-body descriptor based on distances of atoms
    in the local amny-body environment.

    Args:
        distances (np.ndarray): distances between atoms i and j
        r_cut (float): cutoff hyperparameter
        cutoff_func (callable): cutoff function
        q_func (callable): many-body pairwise descrptor function

    Return:
        float: the value of the many-body descriptor
    """
    q = 0

    for d in distances:
        q_, _ = q_func(d, 0, r_cut, cutoff_func)
        q += q_

    return q


@njit
def mb_grad_helper_ls_(qdiffsq, sig, ls):
    """Derivative of a many body force-force kernel wrt ls

    """

    ls2 = ls * ls

    prefact = exp(-(qdiffsq / (2 * ls2))) * (sig * sig) / ls ** 5

    ret = - prefact * (qdiffsq ** 2 / ls2 - 5 * qdiffsq + 2 * ls2)

    return ret

@njit


def mb_grad_helper_ls(q1, q2, qi, qj, sig, ls):
    """Helper function fr many body gradient collecting all the derivatives
    of the force-foce many body kernel wrt ls

    """

    q12diffsq = ((q1 - q2) * (q1 - q2))
    qijdiffsq = ((qi - qj) * (qi - qj))
    qi2diffsq = ((qi - q2) * (qi - q2))
    q1jdiffsq = ((q1 - qj) * (q1 - qj))

    dk12 = mb_grad_helper_ls_(q12diffsq, sig, ls)
    dkij = mb_grad_helper_ls_(qijdiffsq, sig, ls)
    dki2 = mb_grad_helper_ls_(qi2diffsq, sig, ls)
    dk1j = mb_grad_helper_ls_(q1jdiffsq, sig, ls)

    return dk12 + dkij + dki2 + dk1j


_str_to_kernel = {'two_body': two_body,
                  'two_body_en': two_body_en,
                  'two_body_force_en': two_body_force_en,
                  'three_body': three_body,
                  'three_body_en': three_body_en,
                  'three_body_force_en': three_body_force_en,
                  'two_plus_three_body': two_plus_three_body,
                  'two_plus_three_en': two_plus_three_en,
                  'two_plus_three_force_en': two_plus_three_force_en,
                  '2': two_body,
                  '2_en': two_body_en,
                  '2_grad': two_body_grad,
                  '2_force_en': two_body_force_en,
                  '2_efs_energy': None,
                  '2_efs_force': None,
                  '3': three_body,
                  '3_grad': three_body_grad,
                  '3_en': three_body_en,
                  '3_force_en': three_body_force_en,
                  '3_efs_energy': None,
                  '3_efs_force': None,
                  '2+3': two_plus_three_body,
                  '2+3_grad': two_plus_three_body_grad,
                  '2+3_en': two_plus_three_en,
                  '2+3_force_en': two_plus_three_force_en,
                  '2+3_efs_energy': None,
                  '2+3_efs_force': None,
                  'many': many_body,
                  'many_en': many_body_en,
                  'many_grad': many_body_grad,
                  'many_force_en': many_body_force_en,
                  'many_efs_energy': None,
                  'many_efs_force': None,
                  'two_plus_three_plus_many_body':
                  two_plus_three_plus_many_body,
                  'two_plus_three_plus_many_body_grad':
                  two_plus_three_plus_many_body_grad,
                  'two_plus_three_plus_many_body_en':
                  two_plus_three_plus_many_body_en,
                  'two_plus_three_plus_many_body_force_en':
                  two_plus_three_plus_many_body_force_en,
                  '2+3+many': two_plus_three_plus_many_body,
                  '2+3+many_grad': two_plus_three_plus_many_body_grad,
                  '2+3+many_en': two_plus_three_plus_many_body_en,
                  '2+3+many_force_en': two_plus_three_plus_many_body_force_en,
                  '2+3+many_efs_energy': None,
                  '2+3+many_efs_force': None
                  }


def str_to_kernel(string: str, include_grad: bool = False):
    if string not in _str_to_kernel.keys():
        raise ValueError("Kernel {} not found in list of available "
                         "kernels{}:".format(string, _str_to_kernel.keys()))

    if not include_grad:
        return _str_to_kernel[string]
    else:
        if 'two' in string and 'three' in string:
            return _str_to_kernel[string], two_plus_three_body_grad
        elif 'two' in string and 'three' not in string:
            return _str_to_kernel[string], two_body_grad
        elif 'two' not in string and 'three' in string:
            return _str_to_kernel[string], three_body_grad
        else:
            raise ValueError("Gradient callable for {} not found".format(
                string))
