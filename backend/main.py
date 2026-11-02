import os
import subprocess
import threading
import time
import sys
import math
import torch
import cv2
import numpy as np
import mss
from flask import Flask, jsonify, request
from flask_cors import CORS
from ultralytics import YOLO
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QPainter, QColor, QBrush
from PyQt6.QtCore import Qt, pyqtSignal, QObject

app = Flask("Local Privacy Redactor Bridge")
CORS(app)

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
print(f"[*] Acceleration Device: {DEVICE}")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
binary_path = os.path.join(BASE_DIR, "native", "build", "censor_engine")
cxx_proc = None
shutdown_event = threading.Event()

def read_cxx_output(proc):
    while not shutdown_event.is_set():
        output = proc.stdout.readline()
        if output == '' and proc.poll() is not None:
            break
        if output:
            print(f"  {output.strip()}")

if os.path.exists(binary_path):
    cxx_proc = subprocess.Popen(
        [binary_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    cxx_reader_thread = threading.Thread(target=read_cxx_output, args=(cxx_proc,), daemon=True)
    cxx_reader_thread.start()
    print(f"[*] Native C++ Shield linked: {binary_path}")

print("[*] Loading YOLO-World model into local memory...")
model = YOLO("yolov8m-world.pt")

active_targets = []
is_running = False
lock = threading.Lock()

# --- PYQT6 OVERLAY SETUP ---
class Communicator(QObject):
    update_overlay = pyqtSignal(list)

comm = Communicator()

class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowTransparentForInput |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        screen = QApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self.boxes = []

    def update_boxes(self, boxes):
        self.boxes = boxes
        self.update() 

    def paintEvent(self, event):
        painter = QPainter(self)
        
        # Clear the canvas explicitly to prevent macOS graphical tearing/flashing
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        
        painter.setBrush(QBrush(QColor(0, 0, 0, 255))) 
        painter.setPen(Qt.PenStyle.NoPen)
        
        for box in self.boxes:
            x1, y1, x2, y2 = box
            painter.drawRect(x1, y1, x2 - x1, y2 - y1)
# ---------------------------

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "device": DEVICE, "cxx_connected": cxx_proc is not None})

@app.route("/api/v1/preferences", methods=["POST"])
def update_preferences():
    global active_targets, is_running
    req_data = request.get_json(silent=True) or {}
    targets = req_data.get("targets", [])
    
    valid = [t.strip().lower() for t in targets if isinstance(t, str) and len(t.strip()) >= 2]
    
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
                
    return jsonify({"status": "success", "active_rules": active_targets, "running": is_running})

@app.route("/api/v1/preferences", methods=["GET"])
def get_preferences():
    return jsonify({"active_rules": active_targets, "running": is_running})

def detection_worker():
    # Store tracked boxes: {"box": (x1,y1,x2,y2), "hits": int, "last_seen": float}
    tracked_boxes = []
    
    FADE_TIMEOUT = 1.0       # Keep box on screen for 1 second if missed
    MIN_HITS_TO_DRAW = 2     # Must be seen 2 frames in a row to appear (kills flickering)
    SMOOTH_FACTOR = 0.5      # Higher = faster tracking, Lower = smoother but laggier
    MAX_DISTANCE = 150       # If box jumps more than 150px, treat it as a new object

    def get_center(box):
        return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        while not shutdown_event.is_set():
            with lock:
                running = is_running
                targets = list(active_targets)

            if not running or not targets:
                if tracked_boxes:
                    tracked_boxes = []
                    comm.update_overlay.emit([])
                time.sleep(0.1)
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

            current_time = time.time()
            detected_boxes = []
            
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)
                    detected_boxes.append((x1, y1, x2, y2))

            # tracking logic
            matched_indices = set()
            
            for new_box in detected_boxes:
                new_cx, new_cy = get_center(new_box)
                best_dist = float('inf')
                best_idx = -1
                
                # Find the closest old box
                for i, old in enumerate(tracked_boxes):
                    if i in matched_indices: continue
                    old_cx, old_cy = get_center(old["box"])
                    dist = math.hypot(new_cx - old_cx, new_cy - old_cy)
                    
                    if dist < best_dist and dist < MAX_DISTANCE:
                        best_dist = dist
                        best_idx = i

                if best_idx != -1:
                    # Update existing box
                    old_box = tracked_boxes[best_idx]["box"]
                    
                    sx1 = int(old_box[0] * (1 - SMOOTH_FACTOR) + new_box[0] * SMOOTH_FACTOR)
                    sy1 = int(old_box[1] * (1 - SMOOTH_FACTOR) + new_box[1] * SMOOTH_FACTOR)
                    sx2 = int(old_box[2] * (1 - SMOOTH_FACTOR) + new_box[2] * SMOOTH_FACTOR)
                    sy2 = int(old_box[3] * (1 - SMOOTH_FACTOR) + new_box[3] * SMOOTH_FACTOR)
                    
                    tracked_boxes[best_idx]["box"] = (sx1, sy1, sx2, sy2)
                    tracked_boxes[best_idx]["last_seen"] = current_time
                    tracked_boxes[best_idx]["hits"] += 1
                    matched_indices.add(best_idx)
                else:
                    # Brand new box
                    tracked_boxes.append({
                        "box": new_box, 
                        "last_seen": current_time,
                        "hits": 1
                    })

            # Remove boxes that haven't been seen recently
            tracked_boxes = [b for b in tracked_boxes if current_time - b["last_seen"] < FADE_TIMEOUT]

            # Only draw boxes that have passed the minimum hit threshold
            final_boxes = [b["box"] for b in tracked_boxes if b["hits"] >= MIN_HITS_TO_DRAW]

            # Send to C++
            if cxx_proc and cxx_proc.stdin:
                box_strings = [f"{b[0]},{b[1]},{b[2]},{b[3]}" for b in final_boxes]
                payload = f"FRAME:{';'.join(box_strings)}\n" if box_strings else "CLEAR\n"
                try:
                    cxx_proc.stdin.write(payload)
                    cxx_proc.stdin.flush()
                except BrokenPipeError:
                    pass

            # Send to PyQt Overlay
            comm.update_overlay.emit(final_boxes)
            time.sleep(0.01)

def start_server():
    app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False)

if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    worker_thread = threading.Thread(target=detection_worker, daemon=True)
    worker_thread.start()

    print("[*] Privacy Redactor active on http://127.0.0.1:8080")
    print("[*] Censorship overlay is running. Press Ctrl+C in this terminal to quit.")

    qapp = QApplication(sys.argv)
    overlay = OverlayWindow()
    comm.update_overlay.connect(overlay.update_boxes)
    overlay.show()

    try:
        sys.exit(qapp.exec())
    except KeyboardInterrupt:
        print("\n[*] Shutting down...")
        shutdown_event.set()
        if cxx_proc and cxx_proc.stdin:
            try:
                cxx_proc.stdin.write("QUIT\n")
                cxx_proc.stdin.flush()
            except:
                pass
            cxx_proc.terminate()