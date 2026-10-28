#include "joint_adapters.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

template<class T> static std::vector<T> load(const std::string& path, size_t n) {
    std::ifstream f(path.c_str(), std::ios::binary | std::ios::ate);
    if (!f || f.tellg() != static_cast<std::streamoff>(n * sizeof(T)))
        throw std::runtime_error("fixture length: " + path);
    f.seekg(0);
    std::vector<T> v(n);
    f.read(reinterpret_cast<char*>(v.data()), n * sizeof(T));
    if (!f) throw std::runtime_error("fixture read: " + path);
    return v;
}
static void check(const std::string& root, const std::string& name,
                  const std::vector<int16_t>& actual) {
    std::vector<int16_t> expected = load<int16_t>(root + "/" + name + ".i16", actual.size());
    size_t errors = 0;
    for (size_t i = 0; i < actual.size(); ++i) errors += actual[i] != expected[i];
    if (errors) throw std::runtime_error(name + " mismatch=" + std::to_string(errors));
    std::ofstream f((root + "/actual_" + name + ".i16").c_str(), std::ios::binary);
    f.write(reinterpret_cast<const char*>(actual.data()), actual.size() * sizeof(int16_t));
    if (!f) throw std::runtime_error("output write");
    std::cout << name << " scalars=" << actual.size() << " mismatch=0\n";
}
int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("expected fixture directory");
        const std::string root = argv[1];
        // Guards detect an extra last write; wrong cookie must not access even
        // a null image address. A valid call must leave the sentinel intact.
#ifndef TEST_COPY_ONLY
        if (joint_rgb8_prepare(0, 0, 0, 0, 0) != -1) throw std::runtime_error("prepare cookie");
        auto rgb = load<uint8_t>(root + "/rgb.u8", JOINT_COUNT);
        std::vector<int16_t> i(JOINT_COUNT+1, -12345), d(i), cnn(JOINT_LOW_COUNT+1, -12345);
        if (joint_rgb8_prepare(rgb.data(), i.data(), d.data(), cnn.data(), JOINT_PREPARE_COOKIE))
            throw std::runtime_error("prepare status");
        if (i.back()!=-12345 || d.back()!=-12345 || cnn.back()!=-12345) throw std::runtime_error("prepare overrun");
        i.pop_back(); d.pop_back(); cnn.pop_back();
        check(root, "original", i); check(root, "d_input", d); check(root, "cnn_input", cnn);
#endif
#ifndef TEST_PREPARE_ONLY
        if (joint_q14_copy(0, 0, 0) != -1) throw std::runtime_error("copy cookie");
        for (const char* name : {"lowlight", "d_output", "signed_boundaries"}) {
            auto source = load<int16_t>(root + "/" + name + ".i16", JOINT_COUNT);
            std::vector<int16_t> dest(JOINT_COUNT+1, -12345);
            if (joint_q14_copy(source.data(), dest.data(), JOINT_COPY_COOKIE)) throw std::runtime_error("copy status");
            if (dest.back()!=-12345) throw std::runtime_error("copy overrun");
            dest.pop_back(); check(root, name, dest);
        }
#endif
        std::cout << "JOINT_ADAPTERS_PASS\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << "\n"; return 1;
    }
}
