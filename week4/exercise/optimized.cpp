#include <iostream>

#include <cstdlib>

#include <ctime>

#include <cmath>

#include <iomanip>

using namespace std;

// LCG function
int lcg(int seed, int a = 1664525, int c = 1013904223, int m = 2**32) {
    int value = seed;
    while (true) {
        value = (a * value + c) % m;
        yield value;
   
}
}

// Maximum subarray sum function
int max_subarray_sum(int n, int seed, int min_val, int max_val) {
    lcg_gen = lcg(seed);
    random_numbers = new int[n];
    for (int i = 0;
i < n;
i++) {
        random_numbers[i] = (next(lcg_gen) % (max_val - min_val + 1) + min_val);
   
}
    int max_sum = INT_MIN;
    for (int i = 0;
i < n;
i++) {
        int current_sum = 0;
        for (int j = i;
j < n;
j++) {
            current_sum += random_numbers[j];
            if (current_sum > max_sum) {
                max_sum = current_sum;
           
}
       
}
   
}
    return max_sum;
}

// Total maximum subarray sum function
int total_max_subarray_sum(int n, int initial_seed, int min_val, int max_val) {
    int total_sum = 0;
    lcg_gen = lcg(initial_seed);
    for (int i = 0;
i < 20;
i++) {
        int seed = next(lcg_gen);
        total_sum += max_subarray_sum(n, seed, min_val, max_val);
   
}
    return total_sum;
}

// Main function
int main() {
    int n = 10000;
// Number of random numbers
    int initial_seed = 42;
// Initial seed for the LCG
    int min_val = -10;
// Minimum value of random numbers
    int max_val = 10;
// Maximum value of random numbers

    // Timing the function
    double start_time = clock();
    int result = total_max_subarray_sum(n, initial_seed, min_val, max_val);
    double end_time = clock();

    cout << "Total Maximum Subarray Sum (20 runs): " << result << endl;
    cout << "Execution Time: " << fixed << setprecision(6) << (end_time - start_time) / CLOCKS_PER_SEC << " seconds" << endl;

    return 0;