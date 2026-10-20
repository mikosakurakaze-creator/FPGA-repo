#include "weather_kernel.h"
#include "weather_frame.h"
#include <stdint.h>
#include <algorithm>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool ok, const std::string& what) {
    if (!ok) throw std::runtime_error(what);
}
static std::string node_name(int node) {
    if (node == 0) return "input";
    if (node == 1) return "stem";
    if (node == 2) return "stem_relu";
    if (node == 28) return "tail";
    if (node == 29) return "output";
    const char* suffix[] = {"depth", "depth_relu", "point", "add", "relu"};
    return "blocks." + std::to_string((node - 3) / 5) + "." + suffix[(node - 3) % 5];
}
static std::vector<int16_t> read_le(const std::string& path, size_t count) {
    std::ifstream f(path.c_str(), std::ios::binary);
    require(bool(f), "cannot open: " + path);
    std::vector<int16_t> out(count);
    for (size_t i = 0; i < count; ++i) {
        unsigned char b[2];
        require(bool(f.read(reinterpret_cast<char*>(b), 2)), "short tensor: " + path);
        const uint16_t raw = uint16_t(b[0]) | (uint16_t(b[1]) << 8);
        out[i] = raw < 32768U ? int16_t(raw) : int16_t(int32_t(raw) - 65536);
    }
    char extra;
    require(!f.get(extra), "long tensor: " + path);
    return out;
}
static void write_le(const std::string& path, const std::vector<int16_t>& values) {
    std::ofstream f(path.c_str(), std::ios::binary);
    require(bool(f), "cannot write: " + path);
    for (size_t i = 0; i < values.size(); ++i) {
        uint16_t v = uint16_t(values[i]);
        unsigned char b[] = {static_cast<unsigned char>(v), static_cast<unsigned char>(v >> 8)};
        f.write(reinterpret_cast<const char*>(b), 2);
    }
    require(bool(f), "write failed: " + path);
}
static std::vector<int16_t> make_input(int task, int h, int w, int pattern) {
    std::vector<int16_t> input(size_t(3) * h * w);
    uint32_t state = 0x9173U + uint32_t(task) * 0x10001U + uint32_t(pattern) * 71U;
    const int16_t extremes[] = {-32768, 32767, -1, 0, 1, 16383, 16384, 16385};
    for (size_t i = 0; i < input.size(); ++i) {
        state = state * 1664525U + 1013904223U;
        input[i] = pattern == 1 ? extremes[(i + (state >> 16)) % 8]
            : pattern == 2 ? int16_t(0)
            : pattern == 3 ? int16_t(16384) : int16_t((state >> 8) % 16385U);
    }
    return input;
}
static int run_task(int task, const int16_t* input, int16_t* output, int h, int w) {
    std::vector<int16_t> scratch(size_t(24) * h * w);
    return task == 0 ? derain_top(input, output, scratch.data(), h, w)
                     : dehaze_top(input, output, scratch.data(), h, w);
}
// Independent host gather/scatter with configurable 64/128 core size.
static void reference_frame(int task, const std::vector<int16_t>& input,
                           std::vector<int16_t>& output, int h, int w, int core) {
    for (int y = 0; y < h; y += core) {
        for (int x = 0; x < w; x += core) {
            const int y1 = std::min(y + core, h), x1 = std::min(x + core, w);
            const int y0 = std::max(y - 6, 0), x0 = std::max(x - 6, 0);
            const int ye = std::min(y1 + 6, h), xe = std::min(x1 + 6, w);
            const int th = ye - y0, tw = xe - x0;
            std::vector<int16_t> ti(3 * th * tw), to(3 * th * tw);
            for (int c = 0; c < 3; ++c)
                for (int ty = 0; ty < th; ++ty)
                    for (int tx = 0; tx < tw; ++tx)
                        ti[(c * th + ty) * tw + tx] = input[(c * h + y0 + ty) * w + x0 + tx];
            require(run_task(task, ti.data(), to.data(), th, tw) == 0, "reference status");
            for (int c = 0; c < 3; ++c)
                for (int ty = y; ty < y1; ++ty)
                    for (int tx = x; tx < x1; ++tx)
                        output[(c * h + ty) * w + tx] = to[(c * th + ty - y0) * tw + tx - x0];
        }
    }
}
static void compare(const std::vector<int16_t>& a, const std::vector<int16_t>& b,
                    const std::string& context) {
    require(a.size() == b.size(), context + " size");
    for (size_t i = 0; i < a.size(); ++i)
        if (a[i] != b[i]) throw std::runtime_error(context + " index=" + std::to_string(i)
            + " expected=" + std::to_string(a[i]) + " actual=" + std::to_string(b[i]));
}
static void check_frame(int task, int h, int w, int pattern, int core = 128) {
    const std::vector<int16_t> input = make_input(task, h, w, pattern);
    const std::vector<int16_t> saved = input;
    std::vector<int16_t> expected(input.size()), guarded(input.size() + 32, int16_t(-12345));
    reference_frame(task, input, expected, h, w, core);
    require(weather_frame_top(input.data(), guarded.data() + 16, h, w, task) == 0, "frame status");
    compare(expected, std::vector<int16_t>(guarded.begin() + 16, guarded.end() - 16), "frame mismatch");
    compare(saved, input, "input modified");
    for (int i = 0; i < 16; ++i)
        require(guarded[i] == -12345 && guarded[guarded.size() - 1 - i] == -12345, "output guard damaged");
    std::cout << "FRAME_EXACT task=" << task << " shape=" << h << "x" << w
              << " pattern=" << pattern << " reference_core=" << core << "\n";
}
struct TraceData {
    std::vector<int16_t> expected[30], actual[30];
    std::vector<unsigned char> seen[30];
    int h, w, next;
    TraceData(int height, int width) : h(height), w(width), next(0) {}
};
static void reference_trace(const char* name, const int16_t* values, int ch, int h, int w, void* user) {
    TraceData& d = *static_cast<TraceData*>(user);
    require(d.next < 30 && node_name(d.next) == name && h == d.h && w == d.w, "reference trace order");
    d.expected[d.next].assign(values, values + ch * h * w);
    d.actual[d.next].resize(ch * h * w);
    d.seen[d.next].assign(ch * h * w, 0);
    ++d.next;
}
static void optimized_trace(int node, int c, int y, int x, int16_t v, void* user) {
    TraceData& d = *static_cast<TraceData*>(user);
    require(node >= 0 && node < 30 && c >= 0 && y >= 0 && y < d.h && x >= 0 && x < d.w, "trace coordinates");
    const size_t i = size_t(c * d.h + y) * d.w + x;
    require(i < d.expected[node].size() && d.seen[node][i] == 0, "trace repeated/out of bounds");
    require(d.expected[node][i] == v, "trace mismatch node=" + node_name(node) + " index=" + std::to_string(i));
    d.actual[node][i] = v;
    d.seen[node][i] = 1;
}
static void check_trace(int task, int h, int w, const std::vector<int16_t>& input,
                        const std::string& dump = "") {
    TraceData d(h, w);
    std::vector<int16_t> expected(input.size()), actual(input.size());
    weather::set_trace_callback(reference_trace, &d);
    require(run_task(task, input.data(), expected.data(), h, w) == 0, "reference tile status");
    weather::set_trace_callback(0, 0);
    require(d.next == 30, "missing reference nodes");
    weather_b::set_trace(optimized_trace, &d);
    require(weather_b::tile_local(input.data(), actual.data(), h, w, task) == 0, "optimized tile status");
    weather_b::set_trace(0, 0);
    for (int n = 0; n < 30; ++n) {
        require(std::find(d.seen[n].begin(), d.seen[n].end(), 0) == d.seen[n].end(), "missing trace scalar");
        if (!dump.empty()) write_le(dump + "/" + node_name(n) + ".bin", d.actual[n]);
    }
    compare(expected, actual, "tile output");
    std::cout << "ALL_30_NODES_EXACT task=" << task << " shape=" << h << "x" << w << "\n";
}
static void invalid_calls() {
    const int dims[][2] = {{0,1},{1,0},{-1,1},{1,-1},{721,1},{1,1281},{720,1281}};
    for (const auto& d : dims)
        require(weather_frame_top(0, 0, d[0], d[1], 0) == 1, "invalid dimensions accessed pointers/status");
    for (int task : {-1,2,std::numeric_limits<int>::max()})
        require(weather_frame_top(0, 0, 1, 1, task) == 2, "invalid task accessed pointers/status");
    require(weather_frame_top(0, 0, 0, 0, -1) == 1, "dimension status precedence");
    std::cout << "INVALID_CALLS_EXACT cases=11\n";
}
int main(int argc, char** argv) {
    try {
        const std::string mode = argc > 1 ? argv[1] : "";
        if (mode == "selftest" && argc == 2) {
            invalid_calls();
            const int shapes[][2] = {{1,1},{7,11},{140,140}};
            for (int task = 0; task < 2; ++task) {
                for (const auto& s : shapes)
                    for (int pattern = 0; pattern < 2; ++pattern)
                        check_trace(task, s[0], s[1], make_input(task,s[0],s[1],pattern));
                for (int pattern = 0; pattern < 4; ++pattern) check_frame(task,145,149,pattern);
                check_frame(task,145,149,0,64);
                check_frame(task,1,1280,1);
                check_frame(task,720,1,1);
            }
            for (int i = 0; i < 6; ++i) check_frame(i % 2, i % 2 ? 7 : 131, i % 2 ? 11 : 133, i % 4);
            std::cout << "HOST_SUITE_PASS\n"; return 0;
        }
        if (mode == "reference" && argc == 7) {
            check_frame(std::stoi(argv[2]),std::stoi(argv[3]),std::stoi(argv[4]),std::stoi(argv[5]),std::stoi(argv[6]));
            return 0;
        }
        if (mode == "fixture" && argc == 7) {
            int task=std::stoi(argv[2]),h=std::stoi(argv[3]),w=std::stoi(argv[4]);
            const auto input=read_le(argv[5],size_t(3)*h*w), expected=read_le(argv[6],size_t(3)*h*w);
            std::vector<int16_t> actual(input.size());
            require(weather_frame_top(input.data(),actual.data(),h,w,task)==0,"fixture status");
            compare(expected,actual,"official Golden");
            std::cout << "OFFICIAL_GOLDEN_EXACT task=" << task << "\n"; return 0;
        }
        if (mode == "trace_fixture" && argc == 7) {
            int task=std::stoi(argv[2]),h=std::stoi(argv[3]),w=std::stoi(argv[4]);
            check_trace(task,h,w,read_le(argv[5],size_t(3)*h*w),argv[6]); return 0;
        }
        throw std::runtime_error("usage: selftest | reference TASK H W PATTERN CORE | fixture TASK H W INPUT EXPECTED | trace_fixture TASK H W INPUT DUMP_DIR");
    } catch (const std::exception& e) {
        std::cerr << "test_weather_frame: " << e.what() << "\n"; return 2;
    }
}
