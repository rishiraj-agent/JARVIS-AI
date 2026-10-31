// JARVIS AI — Phase 1 C++ foundation and low-memory hardware probe.
// This program does not load a model, call a network service, or create folders.
// MSVC: cl /nologo /std:c++17 /EHsc /Fo:build\signal.obj signal.cpp /Fe:build\jarvis-foundation.exe
// MinGW: g++ -std=c++17 -O2 -Wall -Wextra -pedantic signal.cpp -ladvapi32 -o build/jarvis-foundation.exe

#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <chrono>
#include <ctime>
#include <thread>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <winreg.h>
#ifdef _MSC_VER
#pragma comment(lib, "advapi32.lib")
#endif
#endif

namespace {
struct Options {
    std::uint64_t minimum_free_memory_mib = 512;
    std::string log_path;
    bool help = false;
};

class Logger {
public:
    explicit Logger(const std::string& path) {
        if (!path.empty()) {
            file_.open(path, std::ios::app);
            if (!file_) throw std::runtime_error("Cannot open the requested log path.");
        }
    }

    void info(const std::string& message) { write("INFO", message); }
    void warning(const std::string& message) { write("WARN", message); }
private:
    std::ofstream file_;

    void write(const char* level, const std::string& message) {
        const auto now = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
        std::tm local_time{};
#ifdef _WIN32
        localtime_s(&local_time, &now);
#else
        localtime_r(&now, &local_time);
#endif
        char stamp[24]{};
        std::strftime(stamp, sizeof(stamp), "%Y-%m-%d %H:%M:%S", &local_time);
        const std::string line = std::string("[") + stamp + "] [" + level + "] " + message;
        std::cout << line << '\n';
        if (file_) { file_ << line << '\n'; file_.flush(); }
    }
};

bool parse_unsigned(const std::string& value, std::uint64_t& result) {
    if (value.empty()) return false;
    for (const char digit : value)
        if (digit < '0' || digit > '9') return false;
    try {
        std::size_t consumed = 0;
        const auto parsed = std::stoull(value, &consumed, 10);
        if (consumed != value.size()) return false;
        result = parsed;
        return true;
    } catch (const std::exception&) {
        return false;
    }
}

bool parse_options(int argc, char** argv, Options& options, std::string& error) {
    for (int i = 1; i < argc; ++i) {
        const std::string argument = argv[i];
        if (argument == "--help" || argument == "-h") {
            options.help = true;
        } else if (argument == "--min-free-memory-mib" && i + 1 < argc) {
            if (!parse_unsigned(argv[++i], options.minimum_free_memory_mib)) {
                error = "--min-free-memory-mib expects a non-negative integer.";
                return false;
            }
        } else if (argument == "--log" && i + 1 < argc) {
            options.log_path = argv[++i];
            if (options.log_path.empty()) { error = "--log expects a file path."; return false; }
        } else {
            error = "Unknown or incomplete option: " + argument;
            return false;
        }
    }
    return true;
}

void print_help() {
    std::cout << "JARVIS AI Phase 1 — C++ system and memory foundation\n"
              << "Usage: jarvis-foundation [--min-free-memory-mib N] [--log PATH] [--help]\n"
              << "Reports detected hardware and warns when available RAM is below the limit.\n"
              << "Logging is console-only unless an explicit --log path is supplied.\n";
}

#ifdef _WIN32
std::string processor_name() {
    HKEY key = nullptr;
    const wchar_t* path = L"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0";
    if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, path, 0, KEY_QUERY_VALUE, &key) != ERROR_SUCCESS)
        return "unavailable";
    wchar_t value[512]{};
    DWORD bytes = sizeof(value);
    const auto status = RegQueryValueExW(key, L"ProcessorNameString", nullptr, nullptr,
                                         reinterpret_cast<BYTE*>(value), &bytes);
    RegCloseKey(key);
    if (status != ERROR_SUCCESS) return "unavailable";
    const int size = WideCharToMultiByte(CP_UTF8, 0, value, -1, nullptr, 0, nullptr, nullptr);
    if (size <= 1) return "unavailable";
    std::string result(static_cast<std::size_t>(size), '\0');
    WideCharToMultiByte(CP_UTF8, 0, value, -1, result.data(), size, nullptr, nullptr);
    result.pop_back();
    return result;
}
#endif

struct HardwareInfo {
    std::uint64_t total_bytes = 0;
    std::uint64_t available_bytes = 0;
    unsigned logical_processors = 0;
    std::string processor = "unavailable";
    std::string operating_system = "unknown";
};

HardwareInfo detect_hardware() {
    HardwareInfo info;
#ifdef _WIN32
    MEMORYSTATUSEX memory{};
    memory.dwLength = sizeof(memory);
    if (GlobalMemoryStatusEx(&memory)) {
        info.total_bytes = memory.ullTotalPhys;
        info.available_bytes = memory.ullAvailPhys;
    }
    SYSTEM_INFO system{};
    GetNativeSystemInfo(&system);
    info.logical_processors = system.dwNumberOfProcessors;
    info.processor = processor_name();
    info.operating_system = "Windows";
#else
    info.logical_processors = std::thread::hardware_concurrency();
    info.operating_system = "non-Windows host";
#endif
    return info;
}

void report_hardware(const HardwareInfo& info, const Options& options, Logger& logger) {
    const auto mib = std::uint64_t{1024} * 1024;
    logger.info("JARVIS Phase 1 startup check");
    logger.info("Operating system: " + info.operating_system);
    logger.info("Processor: " + info.processor);
    logger.info("Logical processors: " + std::to_string(info.logical_processors));
    if (info.total_bytes == 0) {
        logger.warning("Physical memory information is unavailable; no training memory estimate was made.");
        return;
    }
    logger.info("Physical memory: " + std::to_string(info.total_bytes / mib) + " MiB total; " +
                std::to_string(info.available_bytes / mib) + " MiB available");
    if (info.available_bytes / mib < options.minimum_free_memory_mib) {
        logger.warning("Available RAM is below the configured " +
                       std::to_string(options.minimum_free_memory_mib) +
                       " MiB threshold. Model training is not part of this Phase 1 executable.");
    } else {
        logger.info("Available RAM meets the configured Phase 1 threshold.");
    }
}
} // namespace

int main(int argc, char** argv) {
    Options options;
    std::string error;
    if (!parse_options(argc, argv, options, error)) {
        std::cerr << "JARVIS: " << error << '\n';
        print_help();
        return 2;
    }
    if (options.help) { print_help(); return 0; }
    try {
        Logger logger(options.log_path);
        const HardwareInfo hardware = detect_hardware();
        report_hardware(hardware, options, logger);
        return 0;
    } catch (const std::exception& exception) {
        std::cerr << "JARVIS startup failed: " << exception.what() << '\n';
        return 1;
    }
}
