#include <algorithm>
#include <cstdlib>
#include <exception>
#include <iomanip>
#include <iostream>
#include <string>

#include "../sequential/graph.h"
#include "../sequential/pagerank.h"
#include "pagerank_omp.h"

namespace {

struct ProgramOptions {
    std::string graph_path;
    double damping_factor = 0.85;
    double tolerance = 1e-8;
    int max_iterations = 100;
    int num_threads = 4;
};

ProgramOptions ParseArgs(int argc, char* argv[]) {
    ProgramOptions options;
    for (int index = 1; index < argc; ++index) {
        const std::string arg = argv[index];
        if (arg == "--graph" && index + 1 < argc) {
            options.graph_path = argv[++index];
        } else if (arg == "--damping" && index + 1 < argc) {
            options.damping_factor = std::stod(argv[++index]);
        } else if (arg == "--tol" && index + 1 < argc) {
            options.tolerance = std::stod(argv[++index]);
        } else if (arg == "--max-iter" && index + 1 < argc) {
            options.max_iterations = std::stoi(argv[++index]);
        } else if (arg == "--threads" && index + 1 < argc) {
            options.num_threads = std::stoi(argv[++index]);
        } else if (arg == "--help") {
            std::cout << "Usage: openmp_pagerank --graph <path> [--damping 0.85] [--tol 1e-8] [--max-iter 100] [--threads 4]\n";
            std::exit(0);
        } else {
            std::cerr << "Unknown argument: " << arg << '\n';
            std::exit(1);
        }
    }
    return options;
}

}  // namespace

int main(int argc, char* argv[]) {
    try {
        const auto options = ParseArgs(argc, argv);
        if (options.graph_path.empty()) {
            std::cerr << "Graph path is required. Use --graph <path>.\n";
            return 1;
        }

        sw401::sequential::Graph graph;
        graph.LoadFromEdgeList(options.graph_path);
        const auto sequential_result = sw401::sequential::ComputePageRank(graph, options.damping_factor, options.tolerance, options.max_iterations);
        const auto openmp_result = sw401::openmp::ComputePageRankOpenMP(graph, options.damping_factor, options.tolerance, options.max_iterations, options.num_threads);

        double max_diff = 0.0;
        for (std::size_t idx = 0; idx < sequential_result.ranks.size(); ++idx) {
            max_diff = std::max(max_diff, std::abs(sequential_result.ranks[idx] - openmp_result.ranks[idx]));
        }

        std::cout << "nodes=" << graph.NumNodes() << "\n";
        std::cout << "edges=" << graph.NumEdges() << "\n";
        std::cout << "sequential_iterations=" << sequential_result.iterations << "\n";
        std::cout << "openmp_iterations=" << openmp_result.iterations << "\n";
        std::cout << "max_abs_diff=" << std::setprecision(12) << max_diff << "\n";
        std::cout << "sequential_error=" << sequential_result.error << "\n";
        std::cout << "openmp_error=" << openmp_result.error << "\n";
        std::cout << "top_ranked_nodes=" << std::fixed << std::setprecision(12) << '\n';
        std::size_t limit = std::min<std::size_t>(10, sequential_result.ranks.size());
        for (std::size_t idx = 0; idx < limit; ++idx) {
            std::cout << idx << ": " << sequential_result.ranks[idx] << " | " << openmp_result.ranks[idx] << '\n';
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }
}
