#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <omp.h>

#if defined(__linux__)
#include <sys/resource.h>
#endif

#include "../src/openmp/pagerank_omp.h"
#include "../src/sequential/graph.h"
#include "../src/sequential/pagerank.h"

namespace {

int ParsePositiveInt(const char* value, const std::string& name) {
    const int parsed = std::stoi(value);
    if (parsed <= 0) {
        throw std::invalid_argument(name + " must be positive.");
    }
    return parsed;
}

double RankSum(const std::vector<double>& ranks) {
    return std::accumulate(ranks.begin(), ranks.end(), 0.0);
}

std::string TopRanks(const std::vector<double>& ranks) {
    std::vector<std::size_t> indices(ranks.size());
    std::iota(indices.begin(), indices.end(), 0);
    const std::size_t count = std::min<std::size_t>(10, indices.size());
    std::partial_sort(indices.begin(), indices.begin() + count, indices.end(),
                      [&ranks](std::size_t left, std::size_t right) {
                          if (ranks[left] != ranks[right]) {
                              return ranks[left] > ranks[right];
                          }
                          return left < right;
                      });
    std::ostringstream result;
    result << std::setprecision(17);
    for (std::size_t index = 0; index < count; ++index) {
        if (index != 0) {
            result << ';';
        }
        result << indices[index] << ':' << ranks[indices[index]];
    }
    return result.str();
}

double MaxAbsoluteDifference(const std::vector<double>& left,
                             const std::vector<double>& right) {
    if (left.size() != right.size()) {
        return INFINITY;
    }
    double difference = 0.0;
    for (std::size_t index = 0; index < left.size(); ++index) {
        difference = std::max(difference, std::abs(left[index] - right[index]));
    }
    return difference;
}

}  // namespace

int main(int argc, char* argv[]) {
    if (argc != 8) {
        std::cerr << "Usage: performance_harness <sequential|openmp> <graph> "
                     "<damping> <tolerance> <max_iterations> <threads> "
                     "<comparison_tolerance>\n";
        return 2;
    }

    try {
        const std::string implementation = argv[1];
        if (implementation != "sequential" && implementation != "openmp") {
            throw std::invalid_argument("Implementation must be sequential or openmp.");
        }

        const double damping = std::stod(argv[3]);
        const double tolerance = std::stod(argv[4]);
        const int max_iterations = ParsePositiveInt(argv[5], "Maximum iterations");
        const int requested_threads = ParsePositiveInt(argv[6], "Thread count");
        const double comparison_tolerance = std::stod(argv[7]);
        if (comparison_tolerance <= 0.0) {
            throw std::invalid_argument("Comparison tolerance must be positive.");
        }

        sw401::sequential::Graph graph;
        const auto load_start = std::chrono::steady_clock::now();
        graph.LoadFromEdgeList(argv[2]);
        const auto load_stop = std::chrono::steady_clock::now();
        const double graph_load_seconds =
            std::chrono::duration<double>(load_stop - load_start).count();
        if (graph.NumNodes() == 0 || graph.NumEdges() == 0) {
            throw std::runtime_error("Graph contains no nodes or no directed edges.");
        }

        int actual_threads = 1;
        if (implementation == "openmp") {
            omp_set_dynamic(0);
#pragma omp parallel num_threads(requested_threads)
            {
#pragma omp single
                actual_threads = omp_get_num_threads();
            }
            if (actual_threads != requested_threads) {
                throw std::runtime_error("OpenMP created " + std::to_string(actual_threads) +
                                         " threads; requested " +
                                         std::to_string(requested_threads) + ".");
            }
        }

        std::vector<double> ranks;
        int iterations = 0;
        double error = 0.0;
        double solver_seconds = 0.0;
        int sequential_iterations = 0;
        double sequential_error = 0.0;
        double sequential_rank_sum = 0.0;
        std::string sequential_top10;
        double max_abs_difference = 0.0;
        double verification_seconds = 0.0;

        const auto solver_start = std::chrono::steady_clock::now();
        if (implementation == "sequential") {
            const auto result = sw401::sequential::ComputePageRank(
                graph, damping, tolerance, max_iterations);
            const auto solver_stop = std::chrono::steady_clock::now();
            solver_seconds = std::chrono::duration<double>(solver_stop - solver_start).count();
            ranks = result.ranks;
            iterations = result.iterations;
            error = result.error;
        } else {
            const auto result = sw401::openmp::ComputePageRankOpenMP(
                graph, damping, tolerance, max_iterations, requested_threads);
            const auto solver_stop = std::chrono::steady_clock::now();
            solver_seconds = std::chrono::duration<double>(solver_stop - solver_start).count();
            ranks = result.ranks;
            iterations = result.iterations;
            error = result.error;

            const auto verification_start = std::chrono::steady_clock::now();
            const auto reference = sw401::sequential::ComputePageRank(
                graph, damping, tolerance, max_iterations);
            const auto verification_stop = std::chrono::steady_clock::now();
            verification_seconds =
                std::chrono::duration<double>(verification_stop - verification_start).count();
            sequential_iterations = reference.iterations;
            sequential_error = reference.error;
            sequential_rank_sum = RankSum(reference.ranks);
            sequential_top10 = TopRanks(reference.ranks);
            max_abs_difference = MaxAbsoluteDifference(reference.ranks, ranks);
        }

        const double rank_sum = RankSum(ranks);
        std::cout << std::setprecision(17)
                  << "nodes=" << graph.NumNodes() << '\n'
                  << "edges=" << graph.NumEdges() << '\n'
                  << "graph_load_seconds=" << graph_load_seconds << '\n'
                  << "actual_threads=" << actual_threads << '\n'
                  << "solver_iterations=" << iterations << '\n'
                  << "solver_error=" << error << '\n'
                  << "solver_converged=" << (error < tolerance ? "true" : "false") << '\n'
                  << "rank_sum=" << rank_sum << '\n'
                  << "rank_sum_valid="
                  << (std::abs(rank_sum - 1.0) <= std::max(10.0 * tolerance, 1e-8)
                          ? "true"
                          : "false")
                  << '\n'
                  << "top10=" << TopRanks(ranks) << '\n'
                  << "solver_seconds=" << solver_seconds << '\n'
                  << "average_iteration_seconds="
                  << (iterations > 0 ? solver_seconds / iterations : 0.0) << '\n'
                  << "verification_seconds=" << verification_seconds << '\n'
                  << "sequential_verification_iterations=" << sequential_iterations << '\n'
                  << "sequential_verification_error=" << sequential_error << '\n'
                  << "sequential_verification_converged="
                  << (implementation == "sequential" || sequential_error < tolerance
                          ? "true"
                          : "false")
                  << '\n'
                  << "sequential_verification_rank_sum=" << sequential_rank_sum << '\n'
                  << "sequential_verification_rank_sum_valid="
                  << (implementation == "sequential" ||
                              std::abs(sequential_rank_sum - 1.0) <=
                                  std::max(10.0 * tolerance, 1e-8)
                          ? "true"
                          : "false")
                  << '\n'
                  << "sequential_verification_top10=" << sequential_top10 << '\n'
                  << "max_abs_difference=" << max_abs_difference << '\n'
                  << "iteration_counts_match="
                  << (implementation == "sequential" || iterations == sequential_iterations
                          ? "true"
                          : "false")
                  << '\n'
                  << "numerical_consistency="
                  << (implementation == "sequential" ||
                              max_abs_difference <= comparison_tolerance
                          ? "true"
                          : "false")
                  << '\n'
                  << "comparison_tolerance=" << comparison_tolerance << '\n';

#if defined(__linux__)
        rusage usage{};
        if (getrusage(RUSAGE_SELF, &usage) == 0) {
            std::cout << "peak_rss_kib=" << usage.ru_maxrss << '\n';
        } else {
            std::cout << "peak_rss_kib=unavailable\n";
        }
#else
        std::cout << "peak_rss_kib=unavailable\n";
#endif
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Benchmark harness error: " << error.what() << '\n';
        return 1;
    }
}
