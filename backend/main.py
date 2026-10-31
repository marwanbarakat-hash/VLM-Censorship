import os
import subprocess
import threading
import queue
import time
import torch
import cv2
import numpy as np
import mss
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from ultralytics import YOLO

app = FastAPI(title="Local Privacy Redactor Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
print(f"[*] Acceleration Device: {DEVICE}")

binary_path = os.path.abspath("../native/build/censor_engine")
cxx_proc = None
if os.path.exists(binary_path):
    cxx_proc = subprocess.Popen(
        [binary_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    print(f"[*] Native C++ Shield linked: {binary_path}")

print("[*] Loading YOLO-World model into local memory...")
model = YOLO("yolov8s-world.pt")

active_targets: List[str] = []
is_running = False
lock = threading.Lock()
frame_queue = queue.Queue(maxsize=2)  # Drops old frames if rendering lags

class PreferencesRequest(BaseModel):
    targets: List[str]

@app.get("/")
def health_check():
    return {"status": "ok", "device": DEVICE, "cxx_connected": cxx_proc is not None}

@app.post("/api/v1/preferences")
def update_preferences(req: PreferencesRequest):
    global active_targets, is_running
    valid = [t.strip().lower() for t in req.targets if len(t.strip()) >= 2]
    with lock:
        active_targets = valid
        is_running = len(active_targets) > 0
        if is_running:
            model.set_classes(active_targets)
        elif cxx_proc and cxx_proc.stdin:
            try:
                cxx_proc.stdin.write("CLEAR\n")
                cxx_proc.stdin.flush()
            except BrokenPipeError:
                pass
    return {"status": "success", "active_rules": active_targets, "running": is_running}

@app.get("/api/v1/preferences")
def get_preferences():
    return {"active_rules": active_targets, "running": is_running}

def detection_worker():
    """Runs in background: captures screen, runs YOLO inference, queues frames."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        while True:
            with lock:
                running = is_running
                targets = list(active_targets)

            if not running or not targets:
                time.sleep(0.05)
                continue

            screenshot = sct.grab(monitor)
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)
            h, w = frame.shape[:2]

            results = model.predict(
                frame,
                imgsz=960,
                conf=0.10,
                iou=0.45,
                device=DEVICE,
                verbose=False
            )

            box_strings = []
            for result in results:
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    conf_val = float(box.conf[0])
                    label = result.names[cls_id] if result.names else "target"

                    # Print detection and confidence score
                    print(f"[*] Detected: {label} (confidence: {conf_val:.2f})")

                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)
                    box_strings.append(f"{x1},{y1},{x2},{y2}")

                    roi = frame[y1:y2, x1:x2]
                    if roi.size > 0:
                        kw = max(1, (roi.shape[1] // 5) | 1)
                        kh = max(1, (roi.shape[0] // 5) | 1)
                        frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (kw, kh), 35)

            if cxx_proc and cxx_proc.stdin:
                payload = f"FRAME:{';'.join(box_strings)}\n" if box_strings else "CLEAR\n"
                try:
                    cxx_proc.stdin.write(payload)
                    cxx_proc.stdin.flush()
                except BrokenPipeError:
                    pass

            if not frame_queue.full():
                preview = cv2.resize(frame, (w // 2, h // 2))
                frame_queue.put(preview)

def start_server():
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="warning")

if __name__ == "__main__":
    # Start FastAPI in a background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Start detection in a background thread
    worker_thread = threading.Thread(target=detection_worker, daemon=True)
    worker_thread.start()

    print("[*] Privacy Redactor active on http://127.0.0.1:8080")
    print("[*] Main thread handling Cocoa window events. Press 'q' in the preview window to exit.")

    # Main thread runs OpenCV event loop directly
    while True:
        try:
            frame = frame_queue.get(timeout=0.1)
            cv2.imshow("Privacy Shield Live Feed", frame)
        except queue.Empty:
            # Keep macOS window event pump responsive even with no active frames
            pass

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()