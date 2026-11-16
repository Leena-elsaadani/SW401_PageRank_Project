#include <chrono>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

#include <omp.h>

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

}  // namespace

int main(int argc, char* argv[]) {
    if (argc != 7) {
        std::cerr << "Usage: performance_harness <sequential|openmp> <graph> "
                     "<damping> <tolerance> <max_iterations> <threads>\n";
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

        sw401::sequential::Graph graph;
        graph.LoadFromEdgeList(argv[2]);

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

        const auto start = std::chrono::steady_clock::now();
        std::chrono::steady_clock::time_point stop;
        int iterations = 0;
        double error = 0.0;
        if (implementation == "sequential") {
            const auto result = sw401::sequential::ComputePageRank(
                graph, damping, tolerance, max_iterations);
            stop = std::chrono::steady_clock::now();
            iterations = result.iterations;
            error = result.error;
        } else {
            const auto result = sw401::openmp::ComputePageRankOpenMP(
                graph, damping, tolerance, max_iterations, requested_threads);
            stop = std::chrono::steady_clock::now();
            iterations = result.iterations;
            error = result.error;
        }
        const double elapsed_seconds =
            std::chrono::duration<double>(stop - start).count();

        std::cout << std::setprecision(17)
                  << "nodes=" << graph.NumNodes() << '\n'
                  << "edges=" << graph.NumEdges() << '\n'
                  << "iterations=" << iterations << '\n'
                  << "error=" << error << '\n'
                  << "elapsed_seconds=" << elapsed_seconds << '\n'
                  << "actual_threads=" << actual_threads << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Benchmark harness error: " << error.what() << '\n';
        return 1;
    }
}
