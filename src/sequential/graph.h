#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace sw401 {
namespace sequential {

class Graph {
public:
    Graph() = default;
    explicit Graph(std::size_t node_count);

    void LoadFromEdgeList(const std::string& path);

    std::size_t NumNodes() const noexcept;
    std::size_t NumEdges() const noexcept;
    const std::vector<std::size_t>& RowOffsets() const noexcept;
    const std::vector<int>& ColumnIndices() const noexcept;
    const std::vector<int>& OutDegree() const noexcept;
    bool Empty() const noexcept;

private:
    std::vector<std::size_t> row_offsets_;
    std::vector<int> column_indices_;
    std::vector<int> out_degree_;
};

}  // namespace sequential
}  // namespace sw401
