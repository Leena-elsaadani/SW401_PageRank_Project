#pragma once

#include <cstddef>
#include <vector>

#include "../sequential/graph.h"

namespace sw401 {
namespace openmp {

struct PageRankResult {
    std::vector<double> ranks;
    int iterations = 0;
    double error = 0.0;
    double elapsed_ms = 0.0;
};

PageRankResult ComputePageRankOpenMP(const sequential::Graph& graph,
                                     double damping_factor = 0.85,
                                     double tolerance = 1e-8,
                                     int max_iterations = 100,
                                     int num_threads = 4);

}  // namespace openmp
}  // namespace sw401
