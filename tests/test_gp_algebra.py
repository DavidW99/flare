import time
import pytest
import numpy as np

import flare.gp_algebra
from flare.env import AtomicEnvironment
from flare.kernels.utils import str_to_kernel_set
from flare.struc import Structure
from flare.utils.parameter_helper import ParameterHelper
from flare_o.kernels.utils import str_to_kernel_set as str_to_kernel_set_o
import flare_o.gp_algebra as gpao

from flare.gp_algebra import get_like_grad_from_mats, \
        get_force_block, get_force_energy_block, \
        energy_energy_vector, energy_force_vector, force_force_vector, \
        force_energy_vector, get_kernel_vector, en_kern_vec, \
        get_ky_mat_update, get_ky_and_hyp, get_energy_block, \
        get_Ky_mat, update_force_block, update_energy_block, \
        update_force_energy_block

from tests.fake_gp import get_tstp


@pytest.fixture(scope='module')
def params():

    nenv = 10
    nstruc = 2
    parameters = get_random_training_set(nenv, nstruc)

    yield parameters
    del parameters


def get_random_training_set(nenv, nstruc):
    """Create a random training_set array with parameters
    And generate four different kinds of hyperparameter sets:
    * multi hypper parameters with two twobody type and two threebody type
    * constrained optimization, with noise parameter optimized
    * constrained optimization, without noise parameter optimized
    * simple hyper parameters without multihyps set up
    """

    np.random.seed(0)

    cutoffs = {'twobody':0.8, 'threebody':0.8}
    parameters={'cutoff_twobody': 0.8,
                'cutoff_threebody': 0.8,
                'noise': 0.05}

    # 9 different hyper-parameters
    pm = ParameterHelper(species=['H', 'He'],
                         kernels={'twobody':[['*', '*'], ['H', 'H']],
                                  'threebody':[['*', '*', '*'],
                                               ['H', 'H', 'H']]},
                         parameters=parameters,
                         ones=True, random=False,
                         verbose="INFO")
    hyps_mask1 = pm.as_dict()

    # 9 different hyper-parameters, onlye train the 0, 2, 4, 6, 8
    pm.set_constraints('twobody0', [True, True])
    pm.set_constraints('twobody1', [False, False])
    pm.set_constraints('threebody0', [True, True])
    pm.set_constraints('threebody1', [False, False])
    hyps_mask2 = pm.as_dict()

    # 9 different hyper-parameters, only train the 0, 2, 4, 6
    pm.set_constraints('noise', False)
    hyps_mask3 = pm.as_dict()

    # 5 different hyper-parameters, equivalent to no multihyps
    pm = ParameterHelper(species=['H', 'He'],
                         kernels={'twobody':[['*', '*']],
                                  'threebody':[['*', '*', '*']]},
                         parameters=parameters,
                         ones=True, random=False,
                         verbose="INFO")
    hyps_mask4 = pm.as_dict()

    # 5 different hyper-parameters, no multihyps
    pm = ParameterHelper(kernels=['twobody', 'threebody'],
                         parameters=parameters,
                         ones=True, random=False,
                         verbose="INFO")
    hyps_mask5 = pm.as_dict()

    hyps_mask_list = [hyps_mask1, hyps_mask2, hyps_mask3, hyps_mask4, hyps_mask5]

    # create training environments and forces
    cell = np.eye(3)
    unique_species = [0, 1, 2, 3]
    noa = 20
    training_data = []
    training_labels = []
    for _ in range(nenv):
        positions = np.random.uniform(-1, 1, [noa, 3])
        species = np.random.randint(0, len(unique_species), noa) + 1
        struc = Structure(cell, species, positions)
        training_data += [AtomicEnvironment(struc, 1, cutoffs)]
        training_labels += [np.random.uniform(-1, 1, 3)]
    training_labels = np.hstack(training_labels)

    # create training structures and energies
    training_structures = []
    energy_labels = []
    for _ in range(nstruc):
        positions = np.random.uniform(-1, 1, [noa, 3])
        species = np.random.randint(0, len(unique_species), noa) + 1
        struc = Structure(cell, species, positions)
        struc_envs = []
        for n in range(noa):
            struc_envs.append(AtomicEnvironment(struc, n, cutoffs))
        training_structures.append(struc_envs)
        energy_labels.append(np.random.uniform(-1, 1))
    energy_labels = np.array(energy_labels)

    # store it as global variables
    name = "unit_test"
    flare.gp_algebra._global_training_data[name] = training_data
    flare.gp_algebra._global_training_labels[name] = training_labels
    flare.gp_algebra._global_training_structures[name] = training_structures
    flare.gp_algebra._global_energy_labels[name] = energy_labels

    gpao._global_training_data[name] = training_data
    gpao._global_training_labels[name] = training_labels
    gpao._global_training_structures[name] = training_structures
    gpao._global_energy_labels[name] = energy_labels

    energy_noise = 0.01

    return name, cutoffs, hyps_mask_list, energy_noise


@pytest.fixture(scope='module')
def ky_mat_ref(params):
    name, cutoffs, hyps_mask_list, energy_noise = params

    # get the reference without multi hyps
    hyps_mask = hyps_mask_list[-1]
    hyps = hyps_mask['hyps']
    kernel = str_to_kernel_set(hyps_mask['kernels'], 'mc', hyps_mask)

    time0 = time.time()
    ky_mat0 = get_Ky_mat(hyps, name, kernel[0], kernel[2], kernel[3],
                         energy_noise, cutoffs)
    print("time ky_mat serial", time.time()-time0)

    # parallel version
    time0 = time.time()
    ky_mat = \
        get_Ky_mat(hyps, name, kernel[0], kernel[2], kernel[3],
                   energy_noise, cutoffs, n_cpus=2, n_sample=5)
    print("time ky_mat parallel ", time.time()-time0)

    assert np.isclose(ky_mat, ky_mat0, rtol=1e-3).all(), \
            "parallel implementation is wrong"

    yield ky_mat0
    del ky_mat0

@pytest.mark.parametrize('ihyps', [0, 1])
def test_ky_mat(params, ihyps, ky_mat_ref):

    name, cutoffs, hyps_mask_list, energy_noise = params
    hyps_mask = hyps_mask_list[ihyps]
    hyps = hyps_mask['hyps']
    kernel = str_to_kernel_set(hyps_mask['kernels'], 'mc', hyps_mask)

    # serial implementation
    time0 = time.time()
    ky_mat = get_Ky_mat(hyps, name, kernel[0], kernel[2], kernel[3],
                        energy_noise, cutoffs, hyps_mask)
    print(f"compute ky_mat with multihyps, test {ihyps}, n_cpus=1",
          time.time()-time0)

    assert np.isclose(ky_mat, ky_mat_ref, rtol=1e-3).all(), \
            "multi hyps implementation is wrong"\
            f"with case {ihyps}"

    # parallel implementation
    time0 = time.time()
    ky_mat = get_Ky_mat(hyps, name, kernel[0], kernel[2], kernel[3],
                        energy_noise, cutoffs, hyps_mask, n_cpus=2,
                        n_sample=1)
    newtime = time.time()-time0
    print(f"compute ky_mat with multihyps, test {ihyps}, n_cpus=2",
          newtime)
    assert np.isclose(ky_mat, ky_mat_ref, rtol=1e-3).all(), \
            f"multi hyps  parallel implementation is wrong with case {ihyps}"

@pytest.mark.parametrize('ihyps', [0, 1, -1])
def test_ky_mat_update(params, ihyps):

    name, cutoffs, hyps_mask_list, energy_noise = params
    hyps_mask = hyps_mask_list[ihyps]
    hyps = hyps_mask['hyps']
    kernel = str_to_kernel_set(hyps_mask['kernels'], 'mc', hyps_mask)

    # prepare old data set as the starting point
    n = 5
    s = 1
    training_data = flare.gp_algebra._global_training_data[name]
    training_structures = flare.gp_algebra._global_training_structures[name]
    flare.gp_algebra._global_training_data['old'] = training_data[:n]
    flare.gp_algebra._global_training_structures['old'] = \
        training_structures[:s]

    func = [get_Ky_mat, get_ky_mat_update]


    # get the reference
    ky_mat0 = func[0](hyps, name, kernel[0], kernel[2],
                      kernel[3], energy_noise, cutoffs, hyps_mask)
    ky_mat_old = func[0](hyps, 'old', kernel[0], kernel[2],
                         kernel[3], energy_noise, cutoffs, hyps_mask)

    # update
    ky_mat = func[1](ky_mat_old, n, hyps, name, kernel[0], kernel[2],
                     kernel[3], energy_noise, cutoffs, hyps_mask)
    assert np.isclose(ky_mat, ky_mat0, rtol=1e-10).all(), \
            "update function is wrong"

    kernel_o = str_to_kernel_set_o(hyps_mask['kernels'], 'mc', hyps_mask)
    ky_mat_o = gpao.get_ky_mat_update(ky_mat_old, n, hyps, name, kernel_o[0], kernel_o[2],
                                      kernel_o[3], energy_noise, cutoffs, hyps_mask)
    assert np.isclose(ky_mat, ky_mat_o, rtol=1e-5).all()

    # parallel version
    ky_mat = func[1](ky_mat_old, n, hyps, name, kernel[0], kernel[2],
                     kernel[3], energy_noise, cutoffs, hyps_mask, n_cpus=2,
                     n_sample=20)
    assert np.isclose(ky_mat, ky_mat0, rtol=1e-10).all(), \
            "update function is wrong"


@pytest.mark.parametrize('ihyps', [0, 1, -1])
def test_kernel_vector(params, ihyps):

    name, cutoffs, hyps_mask_list, _ = params

    np.random.seed(10)
    test_point = get_tstp()

    size1 = len(flare.gp_algebra._global_training_data[name])
    size2 = len(flare.gp_algebra._global_training_structures[name])

    hyps_mask = hyps_mask_list[ihyps]
    hyps = hyps_mask['hyps']
    kernel = str_to_kernel_set(hyps_mask['kernels'], 'mc', hyps_mask)

    # test the parallel implementation for multihyps
    vec = get_kernel_vector(name, kernel[0], kernel[3], test_point,
                            hyps, cutoffs, hyps_mask)

    kernel_o = str_to_kernel_set_o(hyps_mask['kernels'], 'mc', hyps_mask)
    vec_o = gpao.get_kernel_vector(name, kernel_o[0], kernel_o[3], test_point, 1,
                                   hyps, cutoffs, hyps_mask)
    assert np.isclose(vec[:, 0], vec_o, rtol=1e-5).all()

    vec_par = \
        get_kernel_vector(name, kernel[0], kernel[3], test_point, hyps,
                          cutoffs, hyps_mask, n_cpus=2, n_sample=100)

    assert (np.isclose(vec, vec_par, rtol=1e-4).all()), "parallel implementation is wrong"
    assert (vec.shape[0] == size1 * 3 + size2)


@pytest.mark.parametrize('ihyps', [0, 1, -1])
def test_en_kern_vec(params, ihyps):

    name, cutoffs, hyps_mask_list, _ = params
    hyps_mask = hyps_mask_list[ihyps]
    hyps = hyps_mask['hyps']
    kernel = str_to_kernel_set(hyps_mask['kernels'], 'mc', hyps_mask)

    np.random.seed(10)
    test_point = get_tstp()

    size1 = len(flare.gp_algebra._global_training_data[name])
    size2 = len(flare.gp_algebra._global_training_structures[name])

    # test the parallel implementation for multihyps
    vec = en_kern_vec(name, kernel[3], kernel[2], test_point, hyps, cutoffs, hyps_mask)

    kernel_o = str_to_kernel_set_o(hyps_mask['kernels'], 'mc', hyps_mask)
    vec_o = gpao.en_kern_vec(name, kernel_o[3], kernel_o[2], test_point,
                             hyps, cutoffs, hyps_mask)
    assert np.isclose(vec, vec_o, rtol=1e-5).all()

    vec_par = \
        en_kern_vec(name, kernel[3], kernel[2], test_point, hyps, cutoffs, hyps_mask,
                    n_cpus=2, n_sample=100)

    assert (all(np.equal(vec, vec_par))), "parallel implementation is wrong"
    assert (vec.shape[0] == size1 * 3 + size2)


@pytest.mark.parametrize('ihyps', [0, 1, 2, 3, 4])
def test_ky_and_hyp(params, ihyps, ky_mat_ref):

    name, cutoffs, hyps_mask_list, _ = params
    hyps_mask = hyps_mask_list[ihyps]
    hyps = hyps_mask['hyps']
    kernel = str_to_kernel_set(hyps_mask['kernels'], 'mc', hyps_mask)

    func = get_ky_and_hyp

    # first check consistency

    # serial version
    time0=time.time()
    hypmat_ser, ky_mat_ser = func(hyps, name, kernel[1], cutoffs,
                                            hyps_mask)

    # parallel version
    hypmat_par, ky_mat_par = func(hyps, name, kernel[1], cutoffs,
                                            hyps_mask, n_cpus=2)
    # # get_Ky_mat version
    # ky_mat_all = get_Ky_mat(hyps, name, kernel[0], kernel[2],
    #                         kernel[3], 0, cutoffs, hyps_mask)
    ref = ky_mat_ref[:ky_mat_ser.shape[0], :ky_mat_ser.shape[1]]

    assert np.isclose(ky_mat_ser, ref, rtol=1e-5).all(), \
            "serial implementation is not consistent with get_Ky_mat"
    assert np.isclose(ky_mat_par, ref, rtol=1e-5).all(), \
            "parallel implementation is not consistent with get_Ky_mat"
    assert np.isclose(hypmat_ser, hypmat_par, rtol=1e-5).all(), \
            "serial implementation is not consistent with parallel implementation"

    # compare analytical gradient to numerical gradients
    _, like_grad = get_like_grad_from_mats(ky_mat_ser, hypmat_ser, name)

    delta = 0.001
    for i in range(len(hyps)):

        newhyps = np.copy(hyps)

        newhyps[i] += delta
        hyp_mat_p, ky_mat_p = func(newhyps, name, kernel[1],
                                   cutoffs, hyps_mask)
        like_p, _ = \
            get_like_grad_from_mats(ky_mat_p, hyp_mat_p, name)

        newhyps[i] -= 2*delta
        hyp_mat_m, ky_mat_m = func(newhyps, name, kernel[1],
                                   cutoffs, hyps_mask)
        like_m, _ = \
            get_like_grad_from_mats(ky_mat_m, hyp_mat_m, name)

        # numerical form
        numeric = (like_p-like_m)/2./delta
        print(like_grad[i], numeric)
        assert np.isclose(like_grad[i], numeric, rtol=1e-3 ), \
                f"wrong calculation of hyp_mat {i}"

if __name__ == "__main__":

    import cProfile
    import re
    params = get_random_training_set(10, 2)
    cProfile.run('test_ky_and_hyp(params)')
