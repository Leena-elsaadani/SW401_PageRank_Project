#include "graph.h"

#include <algorithm>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace sw401 {
namespace sequential {

Graph::Graph(std::size_t node_count) : row_offsets_(node_count + 1, 0), out_degree_(node_count, 0) {}

void Graph::LoadFromEdgeList(const std::string& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("Unable to open graph file: " + path);
    }

    const std::size_t existing_node_count = (!row_offsets_.empty()) ? (row_offsets_.size() - 1) : 0;
    std::vector<std::pair<int, int>> edges;
    int max_node_id = -1;
    std::string line;

    while (std::getline(input, line)) {
        if (line.empty()) {
            continue;
        }

        const auto comment_pos = line.find('#');
        if (comment_pos == 0) {
            continue;
        }

        if (comment_pos != std::string::npos) {
            line = line.substr(0, comment_pos);
        }

        if (line.find_first_not_of(" \t\r\n") == std::string::npos) {
            continue;
        }

        std::istringstream stream(line);
        int source = 0;
        int target = 0;
        if (!(stream >> source >> target)) {
            continue;
        }

        if (source < 0 || target < 0) {
            continue;
        }

        edges.emplace_back(source, target);
        max_node_id = std::max(max_node_id, std::max(source, target));
    }

    if (edges.empty()) {
        if (existing_node_count > 0) {
            row_offsets_.assign(existing_node_count + 1, 0);
            out_degree_.assign(existing_node_count, 0);
            column_indices_.clear();
            return;
        }

        row_offsets_.clear();
        column_indices_.clear();
        out_degree_.clear();
        return;
    }

    const std::size_t node_count = std::max(existing_node_count, static_cast<std::size_t>(max_node_id + 1));
    row_offsets_.assign(node_count + 1, 0);
    out_degree_.assign(node_count, 0);
    std::vector<int> indegree(node_count, 0);

    for (const auto& edge : edges) {
        const int source = edge.first;
        const int target = edge.second;
        ++out_degree_[static_cast<std::size_t>(source)];
        ++indegree[static_cast<std::size_t>(target)];
    }

    for (std::size_t node = 0; node < node_count; ++node) {
        row_offsets_[node + 1] = row_offsets_[node] + static_cast<std::size_t>(indegree[node]);
    }

    column_indices_.assign(edges.size(), -1);
    std::vector<std::size_t> next_position = row_offsets_;
    for (const auto& edge : edges) {
        const int source = edge.first;
        const int target = edge.second;
        const std::size_t target_index = static_cast<std::size_t>(target);
        column_indices_[next_position[target_index]] = source;
        ++next_position[target_index];
    }
}

std::size_t Graph::NumNodes() const noexcept {
    return row_offsets_.empty() ? 0 : row_offsets_.size() - 1;
}

std::size_t Graph::NumEdges() const noexcept {
    return column_indices_.size();
}

const std::vector<std::size_t>& Graph::RowOffsets() const noexcept {
    return row_offsets_;
}

const std::vector<int>& Graph::ColumnIndices() const noexcept {
    return column_indices_;
}

const std::vector<int>& Graph::OutDegree() const noexcept {
    return out_degree_;
}

bool Graph::Empty() const noexcept {
    return row_offsets_.empty();
}

}  // namespace sequential
}  // namespace sw401
