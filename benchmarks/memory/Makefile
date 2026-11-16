CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -Wpedantic
OMPFLAGS ?= -fopenmp

BUILD_DIR := ../../build/memory
TARGETS := $(BUILD_DIR)/csr_locality $(BUILD_DIR)/false_sharing $(BUILD_DIR)/sync_overhead

.PHONY: all clean test

all: $(TARGETS)

$(BUILD_DIR):
	mkdir -p $@

$(BUILD_DIR)/csr_locality: csr_locality.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $< -o $@

$(BUILD_DIR)/false_sharing: false_sharing.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $(OMPFLAGS) $< -o $@

$(BUILD_DIR)/sync_overhead: sync_overhead.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $(OMPFLAGS) $< -o $@

test: all
	$(BUILD_DIR)/csr_locality ../../tests/data/tiny_graph.txt 2 >/dev/null
	$(BUILD_DIR)/false_sharing 10000 2 >/dev/null
	$(BUILD_DIR)/sync_overhead 100 2 >/dev/null

clean:
	rm -f $(TARGETS)
