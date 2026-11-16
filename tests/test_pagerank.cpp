#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "../src/openmp/pagerank_omp.h"
#include "../src/sequential/graph.h"
#include "../src/sequential/pagerank.h"

namespace {

void Assert(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

double TotalRank(const std::vector<double>& ranks) {
    double sum = 0.0;
    for (double value : ranks) {
        sum += value;
    }
    return sum;
}

std::string WriteGraphFile(const std::string& name, const std::vector<std::pair<int, int>>& edges) {
    const std::filesystem::path directory = "/tmp/sw401_pagerank_tests";
    std::filesystem::create_directories(directory);
    const std::filesystem::path path = directory / name;

    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("Failed to create temporary graph file: " + path.string());
    }

    for (const auto& edge : edges) {
        output << edge.first << ' ' << edge.second << '\n';
    }

    return path.string();
}

void TestSimpleGraph() {
    const auto path = WriteGraphFile("simple_graph.txt", {{0, 1}, {1, 0}, {1, 2}});
    sw401::sequential::Graph graph;
    graph.LoadFromEdgeList(path);
    const auto sequential_result = sw401::sequential::ComputePageRank(graph, 0.85, 1e-12, 1000);
    const auto openmp_result = sw401::openmp::ComputePageRankOpenMP(graph, 0.85, 1e-12, 1000, 2);

    Assert(graph.NumNodes() == 3, "Simple graph node count mismatch.");
    Assert(std::abs(TotalRank(sequential_result.ranks) - 1.0) < 1e-9, "Sequential ranks must sum to 1.0.");
    Assert(std::abs(TotalRank(openmp_result.ranks) - 1.0) < 1e-9, "OpenMP ranks must sum to 1.0.");
    Assert(sequential_result.iterations > 0, "Sequential solver did not iterate.");
    Assert(openmp_result.iterations > 0, "OpenMP solver did not iterate.");
    const double max_diff = [&]() {
        double diff = 0.0;
        for (std::size_t index = 0; index < sequential_result.ranks.size(); ++index) {
            diff = std::max(diff, std::abs(sequential_result.ranks[index] - openmp_result.ranks[index]));
        }
        return diff;
    }();
    Assert(max_diff < 1e-10, "Sequential and OpenMP results differ beyond tolerance.");
}

void TestGraphNodeCountPreserved() {
    const std::filesystem::path empty_path = "/tmp/sw401_pagerank_tests/empty_graph.txt";
    std::ofstream empty_file(empty_path);
    empty_file.close();

    sw401::sequential::Graph explicit_graph(5);
    explicit_graph.LoadFromEdgeList(empty_path.string());
    Assert(explicit_graph.NumNodes() == 5, "Explicit node count must be preserved for an empty edge list.");
    Assert(std::abs(static_cast<double>(explicit_graph.NumEdges())) < 1e-9, "Empty graph should not create edges.");

    const auto edge_beyond_path = WriteGraphFile("edge_beyond_explicit_count.txt", {{0, 3}});
    sw401::sequential::Graph expanded_graph(2);
    expanded_graph.LoadFromEdgeList(edge_beyond_path);
    Assert(expanded_graph.NumNodes() == 4, "Node count must expand to include referenced destination IDs.");
    Assert(expanded_graph.OutDegree()[0] == 1, "Out-degree for node 0 should count the edge.");
}

void TestDanglingNode() {
    const auto path = WriteGraphFile("dangling_graph.txt", {{0, 1}, {1, 2}});
    sw401::sequential::Graph graph;
    graph.LoadFromEdgeList(path);

    const auto sequential_result = sw401::sequential::ComputePageRank(graph, 0.85, 1e-12, 1000);
    const auto openmp_result = sw401::openmp::ComputePageRankOpenMP(graph, 0.85, 1e-12, 1000, 2);

    Assert(graph.NumNodes() == 3, "Dangling graph should have three nodes.");
    Assert(graph.OutDegree()[2] == 0, "Node 2 must be a true dangling node.");
    Assert(std::abs(TotalRank(sequential_result.ranks) - 1.0) < 1e-9, "Sequential dangling-node ranks must sum to 1.0.");
    Assert(std::abs(TotalRank(openmp_result.ranks) - 1.0) < 1e-9, "OpenMP dangling-node ranks must sum to 1.0.");
    Assert(sequential_result.ranks[2] > 0.0, "Dangling node should receive redistributed rank.");
    const double max_diff = [&]() {
        double diff = 0.0;
        for (std::size_t index = 0; index < sequential_result.ranks.size(); ++index) {
            diff = std::max(diff, std::abs(sequential_result.ranks[index] - openmp_result.ranks[index]));
        }
        return diff;
    }();
    Assert(max_diff < 1e-10, "Sequential and OpenMP dangling-node results differ beyond tolerance.");
}

void TestIsolatedNode() {
    const auto path = WriteGraphFile("isolated_graph.txt", {{0, 1}, {1, 0}});
    sw401::sequential::Graph graph(4);
    graph.LoadFromEdgeList(path);

    const auto sequential_result = sw401::sequential::ComputePageRank(graph, 0.85, 1e-12, 1000);
    const auto openmp_result = sw401::openmp::ComputePageRankOpenMP(graph, 0.85, 1e-12, 1000, 2);

    Assert(graph.NumNodes() == 4, "Isolated-node graph should preserve the explicit count.");
    Assert(graph.OutDegree()[2] == 0 && graph.OutDegree()[3] == 0, "Nodes 2 and 3 must be isolated.");
    Assert(std::abs(TotalRank(sequential_result.ranks) - 1.0) < 1e-9, "Sequential isolated-node ranks must sum to 1.0.");
    Assert(std::abs(TotalRank(openmp_result.ranks) - 1.0) < 1e-9, "OpenMP isolated-node ranks must sum to 1.0.");
    const double max_diff = [&]() {
        double diff = 0.0;
        for (std::size_t index = 0; index < sequential_result.ranks.size(); ++index) {
            diff = std::max(diff, std::abs(sequential_result.ranks[index] - openmp_result.ranks[index]));
        }
        return diff;
    }();
    Assert(max_diff < 1e-10, "Sequential and OpenMP isolated-node results differ beyond tolerance.");
}

void TestMultipleIncomingEdges() {
    const auto path = WriteGraphFile("incoming_graph.txt", {{0, 2}, {1, 2}, {2, 3}, {3, 2}});
    sw401::sequential::Graph graph;
    graph.LoadFromEdgeList(path);
    const auto result = sw401::sequential::ComputePageRank(graph, 0.85, 1e-12, 1000);

    Assert(graph.NumNodes() == 4, "Incoming graph node count mismatch.");
    Assert(result.ranks[2] > result.ranks[0], "Node with multiple incoming edges should accumulate higher rank.");
    Assert(std::abs(TotalRank(result.ranks) - 1.0) < 1e-9, "Incoming graph ranks must sum to 1.0.");
}

void TestSelfLoopAndZeroDegreeHandling() {
    const auto path = WriteGraphFile("selfloop_graph.txt", {{0, 0}, {0, 1}, {1, 2}, {3, 3}});
    sw401::sequential::Graph graph;
    graph.LoadFromEdgeList(path);
    const auto result = sw401::sequential::ComputePageRank(graph, 0.85, 1e-12, 1000);

    Assert(graph.NumNodes() == 4, "Self-loop graph should have four nodes.");
    Assert(result.ranks[0] > 0.0, "Self-loop node should keep positive rank.");
    Assert(std::abs(TotalRank(result.ranks) - 1.0) < 1e-9, "Self-loop graph ranks must sum to 1.0.");
}

void TestMaxIterationsReturnsFinalCompletedIteration() {
    const auto path = WriteGraphFile("max_iter_graph.txt", {{0, 1}, {0, 2}, {1, 2}, {2, 0}});
    sw401::sequential::Graph graph;
    graph.LoadFromEdgeList(path);

    const auto sequential_result = sw401::sequential::ComputePageRank(graph, 0.85, 1e-30, 1);
    const auto openmp_result = sw401::openmp::ComputePageRankOpenMP(graph, 0.85, 1e-30, 1, 2);

    Assert(sequential_result.iterations == 1, "Sequential max-iteration test should stop at iteration 1.");
    Assert(openmp_result.iterations == 1, "OpenMP max-iteration test should stop at iteration 1.");
    Assert(sequential_result.error > 1e-30, "Sequential max-iteration case should not converge within one iteration.");
    Assert(openmp_result.error > 1e-30, "OpenMP max-iteration case should not converge within one iteration.");

    const std::vector<double> expected = {1.0 / 3.0, 23.0 / 120.0, 19.0 / 40.0};
    for (std::size_t vertex = 0; vertex < expected.size(); ++vertex) {
        Assert(std::abs(sequential_result.ranks[vertex] - expected[vertex]) < 1e-12, "Sequential max-iteration result does not match the expected final iteration values.");
        Assert(std::abs(openmp_result.ranks[vertex] - expected[vertex]) < 1e-12, "OpenMP max-iteration result does not match the expected final iteration values.");
    }
    const double max_diff = [&]() {
        double diff = 0.0;
        for (std::size_t index = 0; index < expected.size(); ++index) {
            diff = std::max(diff, std::abs(sequential_result.ranks[index] - openmp_result.ranks[index]));
        }
        return diff;
    }();
    Assert(max_diff < 1e-12, "Sequential and OpenMP max-iteration values differ beyond tolerance.");
}

}  // namespace

int main() {
    try {
        TestSimpleGraph();
        TestGraphNodeCountPreserved();
        TestDanglingNode();
        TestIsolatedNode();
        TestMultipleIncomingEdges();
        TestSelfLoopAndZeroDegreeHandling();
        TestMaxIterationsReturnsFinalCompletedIteration();
        std::cout << "All PageRank tests passed." << std::endl;
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Test failed: " << error.what() << std::endl;
        return 1;
    }
}
