#include <iostream>
#include <vector>
#include <cstdint>
#include <chrono>
#include <limits>

// Linear Congruential Generator
class LCG {
public:
    LCG(uint32_t seed) : value(seed) {}
    uint32_t next() {
        value = (a * value + c) % m;
        return value;
    }
private:
    uint32_t value;
    static constexpr uint32_t a = 1664525;
    static constexpr uint32_t c = 1013904223;
    static constexpr uint32_t m = 4294967296; // 2^32
};

int64_t max_subarray_sum(size_t n, uint32_t seed, int min_val, int max_val) {
    LCG lcg(seed);
    std::vector<int> random_numbers(n);
    
    for (size_t i = 0; i < n; ++i) {
        random_numbers[i] = lcg.next() % (max_val - min_val + 1) + min_val;
    }

    int64_t max_sum = std::numeric_limits<int64_t>::min();

    for (size_t i = 0; i < n; ++i) {
        int64_t current_sum = 0;
        for (size_t j = i; j < n; ++j) {
            current_sum += random_numbers[j];
            if (current_sum > max_sum) {
                max_sum = current_sum;
            }
        }
    }
    
    return max_sum;
}

int64_t total_max_subarray_sum(size_t n, uint32_t initial_seed, int min_val, int max_val) {
    int64_t total_sum = 0;
    LCG lcg(initial_seed);
    
    for (int i = 0; i < 20; ++i) {
        uint32_t seed = lcg.next();
        total_sum += max_subarray_sum(n, seed, min_val, max_val);
    }
    
    return total_sum;
}

int main() {
    size_t n = 10000; // Number of random numbers
    uint32_t initial_seed = 42; // Initial seed for the LCG
    int min_val = -10; // Minimum value of random numbers
    int max_val = 10; // Maximum value of random numbers

    auto start_time = std::chrono::high_resolution_clock::now();
    int64_t result = total_max_subarray_sum(n, initial_seed, min_val, max_val);
    auto end_time = std::chrono::high_resolution_clock::now();

    std::chrono::duration<double> exec_time = end_time - start_time;

    std::cout << "Total Maximum Subarray Sum (20 runs): " << result << std::endl;
    std::cout << "Execution Time: " << exec_time.count() << " seconds" << std::endl;

    return 0;
}
