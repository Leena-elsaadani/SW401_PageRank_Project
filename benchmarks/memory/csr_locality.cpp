#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

struct Graph {
    std::vector<std::uint64_t> row_offsets;
    std::vector<std::uint32_t> destinations;
};

bool parse_edge(const std::string& line, std::uint32_t& source,
                std::uint32_t& destination) {
    if (line.empty() || line.front() == '#') {
        return false;
    }

    std::istringstream stream(line);
    std::uint64_t source_value = 0;
    std::uint64_t destination_value = 0;
    std::string extra;
    if (!(stream >> source_value >> destination_value) || (stream >> extra)) {
        return false;
    }
    if (source_value > std::numeric_limits<std::uint32_t>::max() ||
        destination_value > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("node ID exceeds uint32_t range");
    }

    source = static_cast<std::uint32_t>(source_value);
    destination = static_cast<std::uint32_t>(destination_value);
    return true;
}

Graph load_csr(const std::string& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("cannot open dataset: " + path);
    }

    std::vector<std::uint64_t> degrees;
    std::uint64_t edge_count = 0;
    std::string line;
    std::uint32_t source = 0;
    std::uint32_t destination = 0;

    while (std::getline(input, line)) {
        if (!parse_edge(line, source, destination)) {
            continue;
        }
        const std::size_t required =
            static_cast<std::size_t>(std::max(source, destination)) + 1;
        if (degrees.size() < required) {
            degrees.resize(required, 0);
        }
        ++degrees[source];
        ++edge_count;
    }

    Graph graph;
    graph.row_offsets.resize(degrees.size() + 1, 0);
    for (std::size_t node = 0; node < degrees.size(); ++node) {
        graph.row_offsets[node + 1] = graph.row_offsets[node] + degrees[node];
    }
    graph.destinations.resize(edge_count);

    input.clear();
    input.seekg(0);
    std::vector<std::uint64_t> cursor(graph.row_offsets.begin(),
                                      graph.row_offsets.end() - 1);
    while (std::getline(input, line)) {
        if (parse_edge(line, source, destination)) {
            graph.destinations[cursor[source]++] = destination;
        }
    }
    return graph;
}

double scan(const Graph& graph, const std::vector<std::uint32_t>& node_order,
            const std::vector<double>& ranks) {
    double checksum = 0.0;
    for (const std::uint32_t source : node_order) {
        const std::uint64_t begin = graph.row_offsets[source];
        const std::uint64_t end = graph.row_offsets[source + 1];
        for (std::uint64_t edge = begin; edge < end; ++edge) {
            checksum += ranks[graph.destinations[edge]];
        }
    }
    return checksum;
}

void run_mode(const std::string& mode, const Graph& graph,
              const std::vector<std::uint32_t>& order,
              const std::vector<double>& ranks, int repetitions) {
    for (int repetition = 1; repetition <= repetitions; ++repetition) {
        const auto start = Clock::now();
        const double checksum = scan(graph, order, ranks);
        const double seconds =
            std::chrono::duration<double>(Clock::now() - start).count();
        const double rate = graph.destinations.empty()
                                ? 0.0
                                : graph.destinations.size() / seconds;
        std::cout << mode << ',' << repetition << ',' << std::fixed
                  << std::setprecision(9) << seconds << ',' << rate << ','
                  << std::setprecision(6) << checksum << '\n';
    }
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2 || argc > 3) {
        std::cerr << "Usage: " << argv[0] << " EDGE_LIST [REPETITIONS]\n";
        return 2;
    }

    try {
        const int repetitions = argc == 3 ? std::stoi(argv[2]) : 3;
        if (repetitions <= 0) {
            throw std::runtime_error("repetitions must be positive");
        }

        const Graph graph = load_csr(argv[1]);
        const std::size_t node_count = graph.row_offsets.size() - 1;
        std::vector<double> ranks(node_count,
                                  node_count == 0 ? 0.0 : 1.0 / node_count);
        std::vector<std::uint32_t> ordered(node_count);
        std::iota(ordered.begin(), ordered.end(), 0);
        std::vector<std::uint32_t> shuffled = ordered;
        std::mt19937 random(401);
        std::shuffle(shuffled.begin(), shuffled.end(), random);

        std::cerr << "nodes=" << node_count
                  << " edges=" << graph.destinations.size() << '\n';
        std::cout << "mode,repetition,seconds,edges_per_second,checksum\n";
        run_mode("ordered_rows", graph, ordered, ranks, repetitions);
        run_mode("shuffled_rows", graph, shuffled, ranks, repetitions);
    } catch (const std::exception& error) {
        std::cerr << "csr_locality: " << error.what() << '\n';
        return 1;
    }
}
