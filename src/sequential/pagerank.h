#pragma once

#include <cstddef>
#include <vector>

#include "graph.h"

namespace sw401 {
namespace sequential {

struct PageRankResult {
    std::vector<double> ranks;
    int iterations = 0;
    double error = 0.0;
    double elapsed_ms = 0.0;
};

PageRankResult ComputePageRank(const Graph& graph,
                               double damping_factor = 0.85,
                               double tolerance = 1e-8,
                               int max_iterations = 100);

}  // namespace sequential
}  // namespace sw401
