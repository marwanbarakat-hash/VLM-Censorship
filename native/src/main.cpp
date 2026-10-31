#include <iostream>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <mutex>
#include <sstream>
#include <algorithm>
#include <opencv2/opencv.hpp>

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
    std::cout << "[*] C++ Native Memory-Safe Shield Active (ASan Enabled)" << std::endl;

    std::thread listener(stdin_listener);
    listener.detach();

    while (!g_state.should_quit.load()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }

    return 0;
}