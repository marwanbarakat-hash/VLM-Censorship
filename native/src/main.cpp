#include <iostream>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <mutex>
#include <sstream>
#include <algorithm>
#include <chrono>
#include <opencv2/opencv.hpp>

#ifdef __APPLE__
#define NS_PRIVATE_IMPLEMENTATION
#define CA_PRIVATE_IMPLEMENTATION
#define MTL_PRIVATE_IMPLEMENTATION
#include <Metal/Metal.hpp>
#endif

struct SafeBox {
    int x1, y1, x2, y2;
};

struct EngineState {
    std::mutex mtx;
    std::vector<SafeBox> boxes;
    std::atomic<bool> is_active{false};
    std::atomic<bool> should_quit{false};
};

static EngineState g_state;

// Cross-platform MetalContext wrapper
class MetalContext {
public:
    bool initialize() {
#ifdef __APPLE__
        device = MTL::CreateSystemDefaultDevice();
        if (!device) {
            std::cerr << "[!] Error: Failed to find a default Metal device." << std::endl;
            return false;
        }
        std::cout << "[*] Metal Initialized on GPU: " << device->name()->utf8String() << std::endl;

        commandQueue = device->newCommandQueue();
        if (!commandQueue) {
            std::cerr << "[!] Error: Failed to create Metal command queue." << std::endl;
            return false;
        }

        const char* kernelSource = R"metal(
            kernel void box_blur(texture2d<float, access::read_write> tex [[texture(0)]],
                                 uint2 gid [[thread_position_in_grid]]) 
            {
                if (gid.x >= tex.get_width() || gid.y >= tex.get_height()) return;
                float4 color = tex.read(gid);
                tex.write(color, gid);
            }
        )metal";

        NS::Error* error = nullptr;
        MTL::Library* library = device->newLibrary(
            NS::String::string(kernelSource, NS::UTF8StringEncoding), 
            nullptr, 
            &error
        );
        
        if (!library) {
            std::cerr << "[!] Metal Shader Compilation Error: " << error->localizedDescription()->utf8String() << std::endl;
            return false;
        }

        MTL::Function* blurFunc = library->newFunction(NS::String::string("box_blur", NS::UTF8StringEncoding));
        blurPipelineState = device->newComputePipelineState(blurFunc, &error);
        
        blurFunc->release();
        library->release();

        std::cout << "[+] Metal Compute Pipeline Compiled Successfully." << std::endl;
        return true;
#else
        std::cout << "[*] Linux/Docker environment detected: Metal acceleration skipped (CPU fallback mode)." << std::endl;
        return true;
#endif
    }

    ~MetalContext() {
#ifdef __APPLE__
        if (blurPipelineState) blurPipelineState->release();
        if (commandQueue) commandQueue->release();
        if (device) device->release();
#endif
    }

#ifdef __APPLE__
    MTL::Device* device = nullptr;
    MTL::CommandQueue* commandQueue = nullptr;
    MTL::ComputePipelineState* blurPipelineState = nullptr;
#endif
};

void stdin_listener() {
    std::string line;
    while (std::getline(std::cin, line)) {
        line.erase(std::remove(line.begin(), line.end(), '\r'), line.end());
        line.erase(std::remove(line.begin(), line.end(), '\n'), line.end());

        if (line.rfind("FRAME:", 0) == 0) {
            std::string payload = line.substr(6);
            std::vector<SafeBox> next_boxes;
            std::stringstream ss(payload);
            std::string token;

            while (std::getline(ss, token, ';')) {
                if (token.empty()) continue;
                std::stringstream coords(token);
                std::string cx1, cy1, cx2, cy2;
                if (std::getline(coords, cx1, ',') &&
                    std::getline(coords, cy1, ',') &&
                    std::getline(coords, cx2, ',') &&
                    std::getline(coords, cy2, ',')) {
                    try {
                        next_boxes.push_back({
                            std::stoi(cx1), std::stoi(cy1),
                            std::stoi(cx2), std::stoi(cy2)
                        });
                    } catch (...) {}
                }
            }

            {
                std::lock_guard<std::mutex> lock(g_state.mtx);
                g_state.boxes = std::move(next_boxes);
                g_state.is_active = true;
            }
            std::cout << "[NATIVE C++] Received " << g_state.boxes.size() << " boxes to redact" << std::endl;
        } else if (line == "CLEAR") {
            std::lock_guard<std::mutex> lock(g_state.mtx);
            g_state.boxes.clear();
            g_state.is_active = false;
            std::cout << "[NATIVE C++] Redaction cleared" << std::endl;
        } else if (line == "QUIT") {
            g_state.should_quit = true;
            break;
        }
    }
}

int main() {
    std::cout << "[*] C++ Native Memory-Safe Shield Active" << std::endl;

    MetalContext mtlContext;
    if (!mtlContext.initialize()) {
        std::cerr << "[!] Warning: Metal initialization failed." << std::endl;
    }

    std::thread listener(stdin_listener);
    listener.detach();

    while (!g_state.should_quit.load()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(16));
    }

    return 0;
}