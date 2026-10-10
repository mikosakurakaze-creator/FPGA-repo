#include "curve.hpp"

void curve_fp32(float input, float parameter, float rounds[8]) {
    float x = input;
    for (int iteration = 0; iteration < 8; ++iteration) {
        x = x + parameter * (x * x - x);
        rounds[iteration] = x;
    }
}
