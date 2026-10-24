// Independent, integer-only D reference; C++17 standard library, no Torch/NumPy.
// Build: g++ -std=c++17 -O3 -Wall -Wextra -pedantic oracle.cpp -o oracle
// Run: oracle PACKAGE INPUT_I16_LE H W NEW_OUTPUT_DIRECTORY
// Package hashes are authenticated by check_oracle.py before invoking this tool.
// This executable checks the frozen D topology, dimensions, arithmetic bounds,
// little-endian byte lengths, and its portable oracle.txt descriptor itself.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
constexpr int64_t I64MAX = std::numeric_limits<int64_t>::max();
constexpr int64_t I64MIN = std::numeric_limits<int64_t>::min();

static void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

// Magnitude decomposition avoids abs(INT64_MIN), signed negative shifts, and
// the overflowing common expression (value + rounding_bias) >> shift.
static int64_t round_shift(int64_t value, int shift) {
    require(shift >= -62 && shift <= 62, "shift outside [-62,62]");
    if (shift == 0) return value;
    if (shift < 0) {
        const int64_t multiplier = int64_t(1) << -shift;
        require(value >= I64MIN / multiplier && value <= I64MAX / multiplier,
                "INT64 left-shift overflow");
        return value * multiplier;
    }
    const uint64_t magnitude = value < 0 ? uint64_t(0) - uint64_t(value) : uint64_t(value);
    uint64_t quotient = magnitude >> shift;
    const uint64_t remainder = magnitude & ((uint64_t(1) << shift) - 1);
    if (remainder >= (uint64_t(1) << (shift - 1))) ++quotient;
    // A right shift of at least one makes the rounded magnitude <= 2^62.
    return value < 0 ? -int64_t(quotient) : int64_t(quotient);
}

static int16_t sat16(int64_t value) {
    return int16_t(std::max<int64_t>(-32768, std::min<int64_t>(32767, value)));
}

static std::vector<uint8_t> read_bytes(const fs::path& path) {
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    require(bool(input), "cannot open input: " + path.string());
    const auto length = input.tellg();
    require(length >= 0, "cannot determine byte length");
    std::vector<uint8_t> bytes(static_cast<size_t>(length));
    input.seekg(0);
    if (!bytes.empty()) input.read(reinterpret_cast<char*>(bytes.data()), std::streamsize(bytes.size()));
    require(bool(input), "short input read: " + path.string());
    return bytes;
}

static int16_t decode_i16(const std::vector<uint8_t>& bytes, size_t offset) {
    require(offset <= bytes.size() && bytes.size() - offset >= 2, "INT16 offset out of bounds");
    const int value = int(bytes[offset]) | (int(bytes[offset + 1]) << 8);
    return int16_t(value < 32768 ? value : value - 65536);
}

static int64_t decode_i64(const std::vector<uint8_t>& bytes, size_t offset) {
    require(offset <= bytes.size() && bytes.size() - offset >= 8, "INT64 offset out of bounds");
    uint64_t value = 0;
    for (int byte = 0; byte < 8; ++byte) value |= uint64_t(bytes[offset + byte]) << (8 * byte);
    return value <= uint64_t(I64MAX) ? int64_t(value) : -int64_t(~value) - 1;
}

struct Tensor {
    int channels = 0;
    int frac = 0;
    std::vector<int16_t> data;
};

struct Node {
    std::string id, op;
    int frac = 0, cout = 0, cin = 0;
    std::vector<std::string> sources;
    std::vector<int> shifts;
    std::vector<int16_t> weights;
    std::vector<int64_t> biases;
};

static std::vector<Node> parse_graph(const fs::path& folder) {
    std::ifstream descriptor(folder / "oracle.txt");
    require(bool(descriptor), "cannot open oracle.txt");
    std::string magic;
    int count = 0;
    require(bool(descriptor >> magic >> count) && magic == "D_INT16_V1" && count == 22,
            "wrong D descriptor identity");
    const auto blob = read_bytes(folder / "parameters.bin");
    std::vector<Node> nodes;
    std::map<std::string, int> channels;
    for (int index = 0; index < count; ++index) {
        Node node;
        int source_count = 0;
        require(bool(descriptor >> node.id >> node.op >> node.frac >> source_count), "truncated node descriptor");
        require(node.frac >= 0 && node.frac <= 14 && source_count >= 0 && source_count <= 2,
                "invalid fraction or source count");
        for (int source = 0; source < source_count; ++source) {
            std::string id;
            require(bool(descriptor >> id) && channels.count(id), "unknown or non-topological source");
            node.sources.push_back(id);
        }
        if (node.op == "conv") {
            uint64_t wo = 0, bo = 0;
            require(bool(descriptor >> node.cout >> node.cin >> wo >> bo), "truncated convolution descriptor");
            require(node.sources.size() == 1 && node.cin == channels.at(node.sources[0]) &&
                    (node.cin == 3 || node.cin == 8) && (node.cout == 3 || node.cout == 8),
                    "invalid D convolution dimensions");
            require(wo % 64 == 0 && bo % 64 == 0 && wo <= blob.size() && bo <= blob.size(),
                    "invalid aligned parameter offsets");
            require(uint64_t(node.cout * node.cin * 9 * 2) <= blob.size() - wo &&
                    uint64_t(node.cout * 8) <= blob.size() - bo, "parameter tensor out of bounds");
            for (int co = 0; co < node.cout; ++co) {
                int shift = 0;
                require(bool(descriptor >> shift) && shift >= -62 && shift <= 62, "invalid convolution shift");
                node.shifts.push_back(shift);
            }
            for (int item = 0; item < node.cout * node.cin * 9; ++item)
                node.weights.push_back(decode_i16(blob, size_t(wo) + 2 * size_t(item)));
            for (int co = 0; co < node.cout; ++co) {
                const int64_t bias = decode_i64(blob, size_t(bo) + 8 * size_t(co));
                const uint64_t abs_bias = bias < 0 ? uint64_t(0) - uint64_t(bias) : uint64_t(bias);
                uint64_t bound = abs_bias;
                require(bound <= uint64_t(I64MAX), "uncertified INT64 bias");
                for (int item = co * node.cin * 9; item < (co + 1) * node.cin * 9; ++item) {
                    const int weight = node.weights[item];
                    const uint64_t term = uint64_t(weight < 0 ? -weight : weight) * 32768;
                    require(bound <= uint64_t(I64MAX) - term, "uncertified INT64 convolution accumulator");
                    bound += term;
                }
                node.biases.push_back(bias);
            }
        } else {
            require(node.op == "input" || node.op == "relu" || node.op == "add" || node.op == "affine", "unknown D op");
            node.cout = node.op == "input" ? 3 : channels.at(node.sources.at(0));
        }
        require(channels.emplace(node.id, node.cout).second, "duplicate node id");
        nodes.push_back(std::move(node));
    }
    std::string extra;
    require(!(descriptor >> extra), "unexpected trailing descriptor tokens");

    // This executable evaluates only the selected eight-convolution D network.
    const std::vector<std::string> ids = {
        "input", "stem.conv", "stem.relu", "block0.conv0", "block0.relu0", "block0.conv1", "block0.add", "block0.relu1",
        "block1.conv0", "block1.relu0", "block1.conv1", "block1.add", "block1.relu1",
        "block2.conv0", "block2.relu0", "block2.conv1", "block2.add", "block2.relu1",
        "head.conv", "input.affine", "output.add", "output.relu"};
    const std::vector<std::string> ops = {
        "input", "conv", "relu", "conv", "relu", "conv", "add", "relu",
        "conv", "relu", "conv", "add", "relu", "conv", "relu", "conv", "add", "relu",
        "conv", "affine", "add", "relu"};
    const std::vector<std::vector<int>> dependencies = {
        {}, {0}, {1}, {2}, {3}, {4}, {2, 5}, {6}, {7}, {8}, {9}, {7, 10}, {11},
        {12}, {13}, {14}, {12, 15}, {16}, {17}, {0}, {19, 18}, {20}};
    for (size_t index = 0; index < nodes.size(); ++index) {
        const Node& node = nodes[index];
        require(node.id == ids[index] && node.op == ops[index], "descriptor is not frozen D topology");
        std::vector<std::string> expected;
        for (int source : dependencies[index]) expected.push_back(ids[source]);
        require(node.sources == expected, "frozen D dependency mismatch at " + node.id);
        require(node.cout == (index == 0 || index >= 18 ? 3 : 8), "frozen D channels mismatch");
        if (node.op == "relu") require(node.frac == nodes[dependencies[index][0]].frac, "ReLU scale mismatch");
    }
    require(nodes[0].frac == 14, "D input must use F14");
    return nodes;
}

static Tensor convolve(const Node& node, const Tensor& input, int height, int width) {
    const size_t plane = size_t(height) * size_t(width);
    Tensor output{node.cout, node.frac, std::vector<int16_t>(size_t(node.cout) * plane)};
    // One independent scalar INT64 dot product per output. Padding is exact zero.
    // No reassociation, SIMD intrinsics, floating-point convolution, or common
    // implementation code with the Python matrix-product reference is used.
    for (int co = 0; co < node.cout; ++co) {
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                int64_t accumulator = node.biases[co];
                for (int ci = 0; ci < node.cin; ++ci) {
                    for (int ky = 0; ky < 3; ++ky) {
                        const int sy = y + ky - 1;
                        if (sy < 0 || sy >= height) continue;
                        for (int kx = 0; kx < 3; ++kx) {
                            const int sx = x + kx - 1;
                            if (sx < 0 || sx >= width) continue;
                            const size_t wi = size_t(((co * node.cin + ci) * 3 + ky) * 3 + kx);
                            const size_t xi = size_t(ci) * plane + size_t(sy) * width + size_t(sx);
                            accumulator += int64_t(input.data[xi]) * node.weights[wi];
                        }
                    }
                }
                output.data[size_t(co) * plane + size_t(y) * width + size_t(x)] =
                    sat16(round_shift(accumulator, node.shifts[co]));
            }
        }
    }
    return output;
}

static void write_tensor(const fs::path& path, const Tensor& tensor) {
    std::ofstream output(path, std::ios::binary);
    require(bool(output), "cannot create node output");
    std::vector<char> bytes(tensor.data.size() * 2);
    for (size_t item = 0; item < tensor.data.size(); ++item) {
        const uint16_t value = uint16_t(tensor.data[item]);
        bytes[2 * item] = char(value & 255);
        bytes[2 * item + 1] = char(value >> 8);
    }
    output.write(bytes.data(), std::streamsize(bytes.size()));
    require(bool(output), "short node output write");
}

static int dimension(const char* text, int maximum) {
    size_t consumed = 0;
    const int value = std::stoi(text, &consumed);
    require(consumed == std::string(text).size() && value >= 1 && value <= maximum, "invalid D image dimension");
    return value;
}

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--arithmetic") {
            int64_t value;
            int shift;
            while (std::cin >> value >> shift) {
                try {
                    const int64_t rounded = round_shift(value, shift);
                    std::cout << rounded << ' ' << sat16(rounded) << '\n';
                } catch (const std::exception&) {
                    std::cout << "ERROR\n";
                }
            }
            require(std::cin.eof(), "invalid arithmetic test input");
            return 0;
        }
        require(argc == 6, "usage: oracle PACKAGE INPUT_I16_LE H W NEW_OUTPUT_DIRECTORY");
        const auto start = std::chrono::steady_clock::now();
        const int height = dimension(argv[3], 720), width = dimension(argv[4], 1280);
        const auto nodes = parse_graph(argv[1]);
        const auto input = read_bytes(argv[2]);
        const size_t input_size = size_t(3) * height * width;
        require(input.size() == input_size * 2, "input must contain exactly NCHW [1,3,H,W] LE INT16");
        Tensor qinput{3, 14, std::vector<int16_t>(input_size)};
        for (size_t item = 0; item < input_size; ++item) {
            qinput.data[item] = decode_i16(input, 2 * item);
            require(qinput.data[item] >= -16384 && qinput.data[item] <= 16384, "input outside normalized F14 range");
        }
        const fs::path out_dir(argv[5]);
        require(!fs::exists(out_dir), "refuse to overwrite oracle output directory");
        require(fs::create_directories(out_dir), "cannot create oracle output directory");
        std::map<std::string, Tensor> values;
        std::map<std::string, int> remaining;
        for (const auto& node : nodes) for (const auto& source : node.sources) ++remaining[source];
        for (size_t index = 0; index < nodes.size(); ++index) {
            const Node& node = nodes[index];
            Tensor value;
            if (node.op == "input") {
                value = std::move(qinput);
            } else if (node.op == "conv") {
                value = convolve(node, values.at(node.sources[0]), height, width);
            } else {
                const Tensor& first = values.at(node.sources[0]);
                value = Tensor{first.channels, node.frac, std::vector<int16_t>(first.data.size())};
                for (size_t item = 0; item < value.data.size(); ++item) {
                    if (node.op == "relu") {
                        value.data[item] = std::max<int16_t>(0, first.data[item]);
                    } else if (node.op == "affine") {
                        value.data[item] = sat16(round_shift(int64_t(first.data[item]) + (int64_t(1) << first.frac),
                                                            first.frac + 1 - node.frac));
                    } else if (node.op == "add") {
                        const Tensor& second = values.at(node.sources[1]);
                        require(second.data.size() == first.data.size(), "add tensor shape mismatch");
                        const int64_t a = round_shift(first.data[item], first.frac - node.frac);
                        const int64_t b = round_shift(second.data[item], second.frac - node.frac);
                        // With F in [0,14] and INT16 operands, |a+b| < 2^31.
                        value.data[item] = sat16(a + b);
                    }
                }
            }
            std::ostringstream filename;
            filename << std::setfill('0') << std::setw(2) << index << '_' << node.id << ".i16";
            write_tensor(out_dir / filename.str(), value);
            values.emplace(node.id, std::move(value));
            for (const auto& source : node.sources) if (--remaining[source] == 0) values.erase(source);
        }
        const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        std::cout << "D_CPP_ORACLE_PASS nodes=22 H=" << height << " W=" << width
                  << " host_seconds=" << std::setprecision(9) << elapsed << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "D_CPP_ORACLE_FAIL: " << error.what() << '\n';
        return 1;
    }
}
