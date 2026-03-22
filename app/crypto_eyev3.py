import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="face_recognition_models")

import os
import threading
import cv2
import numpy as np
from flask import Flask, jsonify
import face_recognition
import sys
import time
import ctypes
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer, Qt
import joblib

# ===================== LOAD ENCODINGS =====================
joblib_file = "embeddings/admin_encodings.joblib"

if not os.path.exists(joblib_file):
    raise FileNotFoundError(f"Joblib file not found: {joblib_file}")

admin_encodings = joblib.load(joblib_file)

if isinstance(admin_encodings, np.ndarray):
    if admin_encodings.ndim == 2 and admin_encodings.shape[1] == 128:
        admin_encodings = [enc for enc in admin_encodings]
    elif admin_encodings.ndim == 1 and admin_encodings.shape[0] % 128 == 0:
        admin_encodings = admin_encodings.reshape(-1, 128).tolist()

if len(admin_encodings) == 0:
    raise ValueError("No admin faces found!")

admin_array = np.stack(admin_encodings)

# ===================== CONFIG =====================
threshold = 0.6
ABSENCE_TIMEOUT = 5
LOCK_COOLDOWN = 10
FOCUS_TIMEOUT = 10

# ===================== GLOBAL STATE =====================
app = Flask(__name__)
last_detection = {"label": "None", "distance": None}

app_qt = QApplication(sys.argv)
app_qt.setQuitOnLastWindowClosed(False)

alert_flag = threading.Event()
stop_monitoring = threading.Event()

last_admin_seen = time.time()
last_focus_seen = time.time()

last_lock_time = 0

alert_type = None
monitoring_paused = False

# 🔥 NEW STATE
focus_alert_active = False

# ===================== FULL SHUTDOWN =====================
def shutdown_app():
    print("🛑 Shutting down application...")
    stop_monitoring.set()
    app_qt.quit()
    os._exit(0)

# ===================== SYSTEM LOCK =====================
def lock_system():
    global last_lock_time, monitoring_paused
    current_time = time.time()

    if current_time - last_lock_time > LOCK_COOLDOWN:
        print("🔒 Locking system!")
        ctypes.windll.user32.LockWorkStation()
        last_lock_time = current_time
        monitoring_paused = True 

# ===================== ALERT POPUP =====================
def show_alert_popup():
    global alert_type, monitoring_paused, last_admin_seen, last_focus_seen, focus_alert_active

    msg = QMessageBox()
    msg.setIcon(QMessageBox.Warning)
    msg.setWindowTitle("⚠️ Security Alert")
    msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)

    if alert_type == "ABSENT":
        msg.setText("👤 Admin not present!\nDo you want to continue monitoring?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.Yes)
        
        result = msg.exec_()

        if result == QMessageBox.Yes:
            print("▶️ Continuing monitoring...")
            monitoring_paused = False
            last_admin_seen = time.time()
            last_focus_seen = time.time()
        else:
            print("⛔ Stopping monitoring...")
            shutdown_app()

    else:
        if alert_type == "UNKNOWN":
            message = "🚨 Unauthorized person detected!"
        elif alert_type == "MULTIPLE":
            message = "👥 Multiple people detected!"
        elif alert_type == "RESUME":
            message = "✅ Admin verified. Monitoring resumed."
        elif alert_type == "FOCUS_LOST":
            message = "👀 You are not focusing on the screen for 20 seconds!"
        else:
            message = "⚠️ Security Alert!"

        msg.setText(message)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()

        # 🔥 Reset focus alert state after popup
        if alert_type == "FOCUS_LOST":
            focus_alert_active = False

        last_admin_seen = time.time()
        last_focus_seen = time.time()

    alert_flag.clear()
    alert_type = None

# ===================== WEBCAM MONITOR =====================
def monitor_webcam():
    global last_detection, last_admin_seen, alert_type, monitoring_paused
    global last_focus_seen, focus_alert_active

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("Cannot open webcam")
        return

    frame_count = 0
    frame_skip = 2

    print("👀 Focus mode started")

    while not stop_monitoring.is_set():
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        if frame_count % frame_skip != 0:
            continue

        small_frame = cv2.resize(frame, (0, 0), fx=0.33, fy=0.33)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_small_frame)

        current_time = time.time()

        # ===================== 🔥 FOCUS MODE =====================
        if not monitoring_paused:

            if face_locations:
                if focus_alert_active:
                    print("✅ Focus regained")
                last_focus_seen = current_time
                focus_alert_active = False

            else:
                idle_time = current_time - last_focus_seen

                if idle_time > FOCUS_TIMEOUT and not focus_alert_active:
                    print(f"⚠️ Focus lost for {int(idle_time)} seconds")
                    alert_type = "FOCUS_LOST"
                    alert_flag.set()
                    focus_alert_active = True

        # ===================== EXISTING LOGIC =====================

        if monitoring_paused:
            if face_locations:
                face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
                for enc in face_encodings:
                    distances = np.linalg.norm(admin_array - enc, axis=1)
                    if len(distances) > 0 and np.min(distances) < threshold:
                        print("✅ Admin returned. Resuming monitoring.")
                        monitoring_paused = False
                        last_admin_seen = time.time()
                        last_focus_seen = time.time()
                        alert_type = "RESUME"
                        alert_flag.set()
                        break
            continue

        if face_locations:
            last_focus_seen = time.time()
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            admin_present = False
            unknown_present = False

            for enc in face_encodings:
                distances = np.linalg.norm(admin_array - enc, axis=1)
                if len(distances) > 0 and np.min(distances) < threshold:
                    admin_present = True
                    last_admin_seen = time.time()
                else:
                    unknown_present = True

            if len(face_encodings) > 1:
                lock_system()
                if not alert_flag.is_set():
                    print("👥 Multiple people detected")
                    alert_type = "MULTIPLE"
                    alert_flag.set()

            elif unknown_present and not admin_present:
                lock_system()
                if not alert_flag.is_set():
                    print("🚨 Unauthorized person detected")
                    alert_type = "UNKNOWN"
                    alert_flag.set()

        else:
            if current_time - last_admin_seen > ABSENCE_TIMEOUT:
                lock_system()
                if not alert_flag.is_set():
                    print("⚠️ Admin absent detected")
                    alert_type = "ABSENT"
                    alert_flag.set()

    cap.release()

# ===================== API =====================
@app.route("/last_detection", methods=["GET"])
def get_last_detection():
    return jsonify(last_detection)

# ===================== ALERT CHECKER =====================
def check_alert():
    if alert_flag.is_set():
        show_alert_popup()

# ===================== STARTUP =====================
timer = QTimer()
timer.timeout.connect(check_alert)
timer.start(500)

threading.Thread(target=monitor_webcam, daemon=True).start()
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False), daemon=True).start()

print("🚀 Security system is running with Advanced Focus Mode (20s)...")
sys.exit(app_qt.exec_())