# Privacy Shield: Real-Time Open-Vocabulary Redaction Engine

A privacy-preserving screen and video redaction system utilizing **YOLO-World** open-vocabulary zero-shot detection, a **FastAPI** control bridge, and a native **C++ memory-safe coordination engine** hardened with LLVM AddressSanitizer (ASan).

The system supports real-time screen capture with Apple Silicon GPU acceleration (`mps`) on macOS, as well as containerized deployment via Docker for headless inference and microservice architectures.

---

## Architecture Overview

```text
 ┌─────────────────┐       HTTP / REST       ┌────────────────────────┐
 │   Frontend UI   │ ──────────────────────> │  FastAPI Server (Py)   │
 │   (Next.js App) │ <────────────────────── │ (0.0.0.0:8080)         │
 └─────────────────┘                         └───────────┬────────────┘
                                                         │
                                               Inter-thread IPC
                                                         │
                                                         ▼
 ┌─────────────────┐      Coordinates Pipe   ┌────────────────────────┐
 │  C++ ASan Core  │ <────────────────────── │ Detection Worker (Py)  │
 │ (censor_engine) │ (FRAME:x1,y1,x2,y2\n)   │  - Screen Capture (mss)│
 └─────────────────┘                         │  - YOLO-World (MPS/CPU)│
                                             │  - Blur / Processing   │
                                             └───────────┬────────────┘
                                                         │
                                                  Queue (maxsize=2)
                                                         │
                                                         ▼
                                             ┌────────────────────────┐
                                             │  Cocoa GUI Main Thread │
                                             │  (cv2.imshow Preview)  │
                                             └────────────────────────┘
```

### Key Components

* **Inference Engine:** YOLO-World (`yolov8s-world.pt`) open-vocabulary detection running on PyTorch with Metal Performance Shaders (`mps`) on macOS or multi-threaded CPU in containerized environments. Dynamic vocabulary reconfiguration via OpenAI CLIP text embeddings.
* **Native C++ Engine (`censor_engine`):** Stateful coordinate parser and bounding-box manager built with Clang 18, CMake, and AddressSanitizer (`-fsanitize=address`) for memory safety.
* **Backend Bridge:** Threaded FastAPI application managing dynamic rule updates, health status, and live frame dispatching.
* **Display / Rendering Pipeline:** Decoupled multi-threaded pipeline using Python `queue.Queue` to push processed frames onto the Cocoa-compliant main thread, avoiding macOS AppKit event pump deadlocks.

---

## Directory Structure

```text
.
├── backend/
│   ├── Dockerfile              # Multi-stage Ubuntu builder + Python slim runtime
│   ├── requirements.txt        # Backend dependencies (FastAPI, YOLO, Torch, CLIP)
│   └── main.py                 # Core server, MPS inference loop, and Cocoa event pump
├── native/
│   ├── CMakeLists.txt          # C++ build script with Clang and ASan flags
│   └── src/
│       └── main.cpp            # Thread-safe coordinate parser and state machine
├── docker-compose.yml          # Container configuration and port bindings
├── .dockerignore               # Container build exclusions
└── .gitignore                  # Git exclusions for models, .venv, and build artifacts
```

---

## Prerequisites

### Native macOS (Recommended for Live Desktop Capture & GPU Acceleration)
* Apple Silicon Mac (M-series) running macOS Sonoma or later
* Python 3.11 or 3.12
* CMake (`brew install cmake`)
* Clang compiler with AddressSanitizer support (Xcode Command Line Tools)
* OpenCV C++ libraries (`brew install opencv`)

### Docker Deployment
* Docker Desktop installed and running
* Docker Compose V2

---

## Getting Started

### Option 1: Native Execution (MPS Acceleration + Desktop Screen Capture)

1. **Set Up Python Environment:**
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. **Build the Native C++ Engine:**
   ```bash
   cd ../native
   mkdir -p build && cd build
   cmake -DCMAKE_CXX_COMPILER=clang++ ..
   cmake --build .
   ```
   *This compiles `censor_engine` with AddressSanitizer active.*

3. **Grant macOS Permissions:**
   Ensure your terminal emulator (Terminal, iTerm2, or VS Code) has **Screen Recording** access:
   * **System Settings > Privacy & Security > Screen & System Audio Recording** -> Toggle **ON**.

4. **Launch the Engine:**
   ```bash
   cd ../../backend
   python main.py
   ```

5. **Interact via API / Swagger:**
   Visit `http://localhost:8080/docs` to configure active targets:
   ```bash
   curl -X 'POST' \
     'http://localhost:8080/api/v1/preferences' \
     -H 'Content-Type: application/json' \
     -d '{"targets": ["person", "cell phone", "dog"]}'
   ```
   *Press `q` while focused on the preview window to cleanly shut down.*

---

### Option 2: Dockerized Backend Service

The Docker setup builds the native C++ binary in a multi-stage Ubuntu container and serves the API for image/frame processing pipelines:

```bash
docker compose up --build
```

Access the interactive API documentation at:
```text
http://localhost:8080/docs
```

> **Note on Docker on macOS:** Docker runs inside a lightweight virtual machine. It does not have access to host macOS display server buffers (`mss`) or Apple Silicon GPU hardware (`mps`), falling back automatically to multi-threaded CPU inference.

---

## API Reference

### Health Check
* **Endpoint:** `GET /`
* **Response:**
  ```json
  {
    "status": "ok",
    "device": "mps",
    "cxx_connected": true
  }
  ```

### Set Redaction Preferences
* **Endpoint:** `POST /api/v1/preferences`
* **Payload:**
  ```json
  {
    "targets": ["person", "dog", "laptop"]
  }
  ```
* **Response:**
  ```json
  {
    "status": "success",
    "active_rules": ["person", "dog", "laptop"],
    "running": true
  }
  ```

### Get Active Rules
* **Endpoint:** `GET /api/v1/preferences`
* **Response:**
  ```json
  {
    "active_rules": ["person", "dog"],
    "running": true
  }
  ```

---

## License

This project is licensed under the MIT License.