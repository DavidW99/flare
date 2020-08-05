#ifndef SINGLE_BOND_H
#define SINGLE_BOND_H

#include <Eigen/Dense>
#include <vector>

class LocalEnvironment;

// Single bond basis functions.
void single_bond_update_env(
    Eigen::VectorXd &single_bond_vals, Eigen::MatrixXd &force_dervs,
    Eigen::MatrixXd &stress_dervs,
    std::function<void(std::vector<double> &, std::vector<double> &, double,
                       int, std::vector<double>)> basis_function,
    std::function<void(std::vector<double> &, double, double,
                       std::vector<double>)> cutoff_function,
    double x, double y, double z, double r, int s, int environment_index,
    int central_index, double rcut, int N, int lmax,
    const std::vector<double> &radial_hyps,
    const std::vector<double> &cutoff_hyps);

void single_bond_sum_env(
    Eigen::VectorXd &single_bond_vals, Eigen::MatrixXd &force_dervs,
    Eigen::MatrixXd &stress_dervs,
    std::function<void(std::vector<double> &, std::vector<double> &, double,
                       int, std::vector<double>)> basis_function,
    std::function<void(std::vector<double> &, double, double,
                       std::vector<double>)> cutoff_function,
    const LocalEnvironment &env, int descriptor_index, int N, int lmax,
    const std::vector<double> &radial_hyps,
    const std::vector<double> &cutoff_hyps);

void from_lammps(double **x, int atom_index, int *type, int inum,
    int *ilist, int *numneigh, int **firstneigh,
    std::function<void(std::vector<double> &, std::vector<double> &, double,
                       int, std::vector<double>)> basis_function,
    void (*cutoff_function)(double *, double, double, std::vector<double>),
    double cutoff, int N, int lmax, Eigen::VectorXd &single_bond_vals,
    Eigen::MatrixXd &environment_force_dervs,
    Eigen::MatrixXd &central_force_dervs);

#endif