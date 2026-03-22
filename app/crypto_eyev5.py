import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="face_recognition_models")

import os
import cv2
import numpy as np
import face_recognition
import sys
import time
import ctypes
import joblib
from PIL import ImageGrab

from pymongo import MongoClient
from bson.binary import Binary

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QTextEdit
)
from PyQt5.QtCore import QTimer

def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # PyInstaller temp folder
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# ===================== MONGODB SETUP =====================
client = MongoClient("mongodb://localhost:27017/")
db = client["security_db"]
collection = db["evidence"]

# ===================== LOAD ENCODINGS =====================
joblib_file = get_resource_path("embeddings/admin_encodings.joblib")

if not os.path.exists(joblib_file):
    raise FileNotFoundError(f"Joblib file not found: {joblib_file}")

admin_encodings = joblib.load(joblib_file)

if isinstance(admin_encodings, np.ndarray):
    if admin_encodings.ndim == 2 and admin_encodings.shape[1] == 128:
        admin_encodings = [enc for enc in admin_encodings]

admin_array = np.stack(admin_encodings)

# ===================== CONFIG =====================
threshold = 0.6
ABSENCE_TIMEOUT = 5
LOCK_COOLDOWN = 10
FOCUS_TIMEOUT = 10
SCREENSHOT_COOLDOWN = 10

# ===================== GLOBAL STATE =====================
last_admin_seen = time.time()
last_focus_seen = time.time()
last_lock_time = 0
last_screenshot_time = 0
focus_alert_active = False

# ===================== STORE IMAGE IN MONGODB =====================
def store_image_in_mongodb(file_path, event_type, img_type):
    try:
        with open(file_path, "rb") as f:
            image_data = f.read()

        document = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event_type,
            "type": img_type,
            "image": Binary(image_data)
        }

        collection.insert_one(document)
        print(f"💾 Stored in MongoDB: {event_type} ({img_type})")

    except Exception as e:
        print("MongoDB Error:", e)

# ===================== EVIDENCE FUNCTIONS =====================
def capture_screenshot(reason="event"):
    global last_screenshot_time

    current_time = time.time()
    if current_time - last_screenshot_time < SCREENSHOT_COOLDOWN:
        return None

    last_screenshot_time = current_time

    folder = "evidence"
    os.makedirs(folder, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{folder}/{reason}_screen_{timestamp}.png"

    screenshot = ImageGrab.grab()
    screenshot.save(filename)

    return filename


def capture_camera_image(frame, reason="event"):
    folder = "evidence"
    os.makedirs(folder, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{folder}/{reason}_camera_{timestamp}.jpg"

    cv2.imwrite(filename, frame)

    return filename


# ===================== UI CLASS =====================
class SecurityApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("AI Security System")
        self.setGeometry(200, 100, 400, 300)

        layout = QVBoxLayout()

        self.status_label = QLabel("Running in Background...")
        layout.addWidget(self.status_label)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        self.setLayout(layout)

        self.cap = cv2.VideoCapture(0)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(200)

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.append(f"[{timestamp}] {message}")
        print(message)

    def update_frame(self):
        global last_admin_seen, last_focus_seen
        global focus_alert_active, last_lock_time

        ret, frame = self.cap.read()
        if not ret:
            return

        small_frame = cv2.resize(frame, (0, 0), fx=0.33, fy=0.33)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_small_frame)
        current_time = time.time()

        admin_present = False
        unknown_present = False

        if face_locations:
            encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            for enc in encodings:
                distances = np.linalg.norm(admin_array - enc, axis=1)

                if np.min(distances) < threshold:
                    admin_present = True
                    last_admin_seen = current_time
                else:
                    unknown_present = True

        # ===================== LOGIC =====================
        if admin_present:
            self.status_label.setText("🟢 Admin Present")
            last_focus_seen = current_time

            if focus_alert_active:
                self.log("✅ Focus regained")
            focus_alert_active = False

        else:
            if current_time - last_admin_seen > ABSENCE_TIMEOUT:
                self.status_label.setText("⚠️ Admin Absent")
                self.lock_system("⚠️ Admin Absent")

            if current_time - last_focus_seen > FOCUS_TIMEOUT and not focus_alert_active:
                self.log("👀 Focus Lost")
                self.status_label.setText("👀 Focus Lost")
                focus_alert_active = True

        # ===================== SECURITY EVENTS =====================
        if len(face_locations) > 1:
            screen = capture_screenshot("multiple_faces")
            cam = capture_camera_image(frame, "multiple_faces")

            if screen:
                store_image_in_mongodb(screen, "multiple_faces", "screenshot")
                self.log("📸 Screen stored")

            store_image_in_mongodb(cam, "multiple_faces", "camera")
            self.log("📷 Camera stored")

            self.lock_system("👥 Multiple people detected")

        elif unknown_present and not admin_present:
            screen = capture_screenshot("unauthorized")
            cam = capture_camera_image(frame, "unauthorized")

            if screen:
                store_image_in_mongodb(screen, "unauthorized", "screenshot")
                self.log("📸 Screen stored")

            store_image_in_mongodb(cam, "unauthorized", "camera")
            self.log("📷 Camera stored")

            self.lock_system("🚨 Unauthorized person detected")

    def lock_system(self, message):
        global last_lock_time

        current_time = time.time()

        if current_time - last_lock_time > LOCK_COOLDOWN:
            self.log(message)
            self.status_label.setText(message)
            ctypes.windll.user32.LockWorkStation()
            last_lock_time = current_time


# ===================== MAIN =====================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = SecurityApp()
    window.hide()  # background mode

    sys.exit(app.exec_())