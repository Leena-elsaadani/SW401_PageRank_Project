#include "pagerank.h"

#include <algorithm>
#include <cmath>
#include <chrono>
#include <stdexcept>
#include <vector>

namespace sw401 {
namespace sequential {

PageRankResult ComputePageRank(const Graph& graph,
                               double damping_factor,
                               double tolerance,
                               int max_iterations) {
    PageRankResult result;
    const std::size_t node_count = graph.NumNodes();
    if (node_count == 0) {
        return result;
    }

    if (damping_factor <= 0.0 || damping_factor >= 1.0) {
        throw std::invalid_argument("Damping factor must be in the open interval (0, 1).");
    }
    if (tolerance <= 0.0) {
        throw std::invalid_argument("Tolerance must be positive.");
    }
    if (max_iterations <= 0) {
        throw std::invalid_argument("Maximum iteration count must be positive.");
    }

    const double base_rank = (1.0 - damping_factor) / static_cast<double>(node_count);
    std::vector<double> previous(node_count, 1.0 / static_cast<double>(node_count));
    std::vector<double> current(node_count, 0.0);

    const auto start_time = std::chrono::steady_clock::now();

    for (int iteration = 1; iteration <= max_iterations; ++iteration) {
        double dangling_rank = 0.0;
        for (std::size_t node = 0; node < node_count; ++node) {
            if (graph.OutDegree()[node] == 0) {
                dangling_rank += previous[node];
            }
        }

        const double dangling_share = damping_factor * dangling_rank / static_cast<double>(node_count);

        for (std::size_t node = 0; node < node_count; ++node) {
            double incoming_sum = 0.0;
            const std::size_t begin = graph.RowOffsets()[node];
            const std::size_t end = graph.RowOffsets()[node + 1];
            for (std::size_t edge_index = begin; edge_index < end; ++edge_index) {
                const int source_node = graph.ColumnIndices()[edge_index];
                const std::size_t source_idx = static_cast<std::size_t>(source_node);
                const int out_degree = graph.OutDegree()[source_idx];
                if (out_degree > 0) {
                    incoming_sum += previous[source_idx] / static_cast<double>(out_degree);
                }
            }
            current[node] = base_rank + dangling_share + damping_factor * incoming_sum;
        }

        double error = 0.0;
        for (std::size_t node = 0; node < node_count; ++node) {
            error += std::abs(current[node] - previous[node]);
        }

        result.iterations = iteration;
        result.error = error;

        if (error < tolerance) {
            result.ranks = current;
            const auto end_time = std::chrono::steady_clock::now();
            const auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);
            result.elapsed_ms = static_cast<double>(elapsed_ms.count());
            return result;
        }

        previous.swap(current);
        std::fill(current.begin(), current.end(), 0.0);
    }

    result.iterations = static_cast<int>(max_iterations);
    result.ranks = previous;
    const auto end_time = std::chrono::steady_clock::now();
    const auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);
    result.elapsed_ms = static_cast<double>(elapsed_ms.count());
    return result;
}

}  // namespace sequential
}  // namespace sw401
