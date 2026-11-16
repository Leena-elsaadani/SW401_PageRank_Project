#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>

#include <omp.h>

namespace {

using Clock = std::chrono::steady_clock;

void measure_barrier(int threads, int rounds) {
    const auto start = Clock::now();
#pragma omp parallel num_threads(threads)
    {
        for (int round = 0; round < rounds; ++round) {
#pragma omp barrier
        }
    }
    const double seconds =
        std::chrono::duration<double>(Clock::now() - start).count();
    std::cout << threads << ",barrier," << std::fixed << std::setprecision(9)
              << seconds << ',' << (seconds * 1e9 / rounds) << '\n';
}

void measure_reduction(int threads, int rounds) {
    double total = 0.0;
    const auto start = Clock::now();
    for (int round = 0; round < rounds; ++round) {
        double round_total = 0.0;
#pragma omp parallel for num_threads(threads) reduction(+ : round_total)
        for (int thread = 0; thread < threads; ++thread) {
            round_total += static_cast<double>(thread + 1);
        }
        total += round_total;
    }
    const double seconds =
        std::chrono::duration<double>(Clock::now() - start).count();
    asm volatile("" : : "g"(total) : "memory");
    std::cout << threads << ",reduction," << std::fixed
              << std::setprecision(9) << seconds << ','
              << (seconds * 1e9 / rounds) << '\n';
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const int rounds = argc >= 2 ? std::stoi(argv[1]) : 10'000;
        const int requested_max = argc >= 3 ? std::stoi(argv[2]) : 8;
        if (argc > 3 || rounds <= 0 || requested_max <= 0) {
            throw std::runtime_error("invalid arguments");
        }
        const int max_threads = std::min(requested_max, omp_get_num_procs());
        const int candidates[] = {1, 2, 4, 8};

        std::cout << "threads,operation,total_seconds,nanoseconds_per_round\n";
        for (const int threads : candidates) {
            if (threads > max_threads) {
                continue;
            }
            measure_barrier(threads, rounds);
            measure_reduction(threads, rounds);
        }
    } catch (const std::exception& error) {
        std::cerr << "Usage: " << argv[0] << " [ROUNDS] [MAX_THREADS]\n"
                  << "sync_overhead: " << error.what() << '\n';
        return 2;
    }
}
