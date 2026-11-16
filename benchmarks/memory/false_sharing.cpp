#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <omp.h>

namespace {

using Clock = std::chrono::steady_clock;

struct PackedCounter {
    std::uint64_t value = 0;
};

struct alignas(64) PaddedCounter {
    std::uint64_t value = 0;
};

template <typename Counter>
void run_layout(const std::string& layout, std::uint64_t iterations,
                int threads) {
    std::vector<Counter> counters(static_cast<std::size_t>(threads));
    const auto start = Clock::now();

#pragma omp parallel num_threads(threads)
    {
        const int thread = omp_get_thread_num();
        std::uint64_t local = counters[thread].value;
        for (std::uint64_t iteration = 0; iteration < iterations; ++iteration) {
            // Force each update to memory; adjacent packed counters then share a
            // cache line even though threads never update the same counter.
            counters[thread].value = ++local;
            asm volatile("" : : "m"(counters[thread].value) : "memory");
        }
    }

    const double seconds =
        std::chrono::duration<double>(Clock::now() - start).count();
    std::uint64_t checksum = 0;
    for (const Counter& counter : counters) {
        checksum += counter.value;
    }
    const double updates = static_cast<double>(iterations) * threads;
    std::cout << threads << ',' << layout << ',' << std::fixed
              << std::setprecision(9) << seconds << ',' << updates / seconds
              << ',' << checksum << '\n';
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const std::uint64_t iterations =
            argc >= 2 ? std::stoull(argv[1]) : 10'000'000ULL;
        const int requested_max = argc >= 3 ? std::stoi(argv[2]) : 8;
        if (argc > 3 || iterations == 0 || requested_max <= 0) {
            throw std::runtime_error("invalid arguments");
        }
        const int max_threads = std::min(requested_max, omp_get_num_procs());
        const int candidates[] = {1, 2, 4, 8};

        std::cout << "threads,layout,seconds,updates_per_second,checksum\n";
        for (const int threads : candidates) {
            if (threads > max_threads) {
                continue;
            }
            run_layout<PackedCounter>("packed", iterations, threads);
            run_layout<PaddedCounter>("cache_line_padded", iterations,
                                      threads);
        }
    } catch (const std::exception& error) {
        std::cerr << "Usage: " << argv[0]
                  << " [ITERATIONS_PER_THREAD] [MAX_THREADS]\n"
                  << "false_sharing: " << error.what() << '\n';
        return 2;
    }
}
