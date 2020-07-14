#include "Structure/structure.h"
#include "gtest/gtest.h"
#include <Eigen/Dense>
#include <cmath>
#include <iostream>

class StructureTest : public ::testing::Test {
public:
  Eigen::MatrixXd cell{3, 3};
  std::vector<int> species{0, 1, 2, 3, 4};
  Eigen::MatrixXd positions{5, 3};
  Structure test_struc;

  std::string radial_string = "chebyshev";
  std::string cutoff_string = "cosine";
  std::vector<double> radial_hyps{0, 5};
  std::vector<double> cutoff_hyps;
  std::vector<int> descriptor_settings{5, 5, 5};
  int descriptor_index = 0;
  double cutoff = 3;
  std::vector<double> many_body_cutoffs{cutoff};

  StructureTest() {
    cell << 4.0, 0.5, 0.8, -1.2, 3.9, 0.73, -0.8, 0.1, 4.1;

    positions << 1.2, 0.7, 2.3, 3.1, 2.5, 8.9, -1.8, -5.8, 3.0, 0.2, 1.1, 2.1,
        3.2, 1.1, 3.3;

    test_struc = Structure(cell, species, positions);
  }
};

TEST_F(StructureTest, TestWrapped) {
  // Check that the wrapped coordinates are equivalent to Cartesian coordinates
  // up to lattice translations.

  // Take positions minus wrapped positions.
  Eigen::MatrixXd wrap_diff =
      test_struc.get_positions() - test_struc.get_wrapped_positions();

  Eigen::MatrixXd cell = test_struc.get_cell();
  Eigen::MatrixXd cell_dot_inverse = (cell * cell.transpose()).inverse();

  Eigen::MatrixXd wrap_rel = (wrap_diff * cell.transpose()) * cell_dot_inverse;

  // Check that it maps to the origin under lattice translations.
  Eigen::MatrixXd check_lat = wrap_rel.array().round() - wrap_rel.array();

  for (int i = 0; i < 5; i++) {
    for (int j = 0; j < 3; j++) {
      EXPECT_LE(abs(check_lat(i, j)), 1e-10);
    }
  }
}
