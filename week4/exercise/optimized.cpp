#include <iostream>
#include <iomanip>
#include <chrono>

int main() {
    // Use long double for higher precision, similar to Python's float
    long double result = 1.0L;
    long long iterations = 100000000LL;
    long long param1 = 4LL;
    long long param2 = 1LL;

    // Use std::chrono for accurate timing
    auto start_time = std::chrono::high_resolution_clock::now();

    // Optimized loop for calculation
    for (long long i = 1LL; i <= iterations; ++i) {
        long double j1 = static_cast<long double>(i) * param1 - param2;
        result -= (1.0L / j1);
        long double j2 = static_cast<long double>(i) * param1 + param2;
        result += (1.0L / j2);
    }

    result *= 4.0L;

    auto end_time = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double> elapsed_time = end_time - start_time;

    // Set precision for output to match Python's .12f
    std::cout << std::fixed << std::setprecision(12);
    std::cout << "Result: " << result << std::endl;

    // Set precision for execution time to match Python's .6f
    std::cout << std::fixed << std::setprecision(6);
    std::cout << "Execution Time: " << elapsed_time.count() << " seconds" << std::endl;

    return 0;
}
