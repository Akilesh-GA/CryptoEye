import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="face_recognition_models")

import os
import threading
import cv2
import numpy as np
from flask import Flask, jsonify
import face_recognition
import sys
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer, Qt
import joblib

joblib_file = "embeddings/admin_encodings.joblib"

if not os.path.exists(joblib_file):
    raise FileNotFoundError(f"❌ Joblib file not found: {joblib_file}")

admin_encodings = joblib.load(joblib_file)

if isinstance(admin_encodings, np.ndarray):
    if admin_encodings.ndim == 2 and admin_encodings.shape[1] == 128:
        admin_encodings = [enc for enc in admin_encodings]
    elif admin_encodings.ndim == 1 and admin_encodings.shape[0] % 128 == 0:
        admin_encodings = admin_encodings.reshape(-1, 128).tolist()

if len(admin_encodings) == 0:
    raise ValueError("❌ No admin faces found in the joblib file!")

threshold = 0.6
app = Flask(__name__)
last_detection = {"label": "None", "distance": None}

app_qt = QApplication(sys.argv)
alert_flag = threading.Event()
stop_monitoring = threading.Event()

def show_alert_popup():
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Warning)
    msg.setWindowTitle("⚠️ Security Alert")
    msg.setText("⚠️ Alert: Unauthorized face detected!")
    msg.setStandardButtons(QMessageBox.Ok)  # Only OK button
    msg.setWindowModality(Qt.ApplicationModal)
    msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
    msg.exec_()
    alert_flag.clear()

def monitor_webcam():
    global last_detection
    cap = cv2.VideoCapture(0)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280) # camera resolution 
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    if not cap.isOpened():
        print("❌ Cannot open webcam")
        return

    frame_count = 0
    frame_skip = 2 

    admin_array = np.stack(admin_encodings)

    while not stop_monitoring.is_set():
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        if frame_count % frame_skip != 0:
            continue

        small_frame = cv2.resize(frame, (0, 0), fx=0.33, fy=0.33) # 0.25
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_small_frame, model="hog") #cnn || hog
        if not face_locations:
            continue

        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations, model="hog")

        alert_triggered = False

        for enc in face_encodings:
            distances = np.linalg.norm(admin_array - enc, axis=1)
            if len(distances) > 0 and np.min(distances) < threshold:
                label = "Admin"
            else:
                label = "Others"
                alert_triggered = True

            last_detection = {
                "label": label,
                "distance": float(np.min(distances)) if len(distances) > 0 else None
            }

            print(f" Detection: {last_detection}")

        if (alert_triggered or len(face_encodings) > 1) and not alert_flag.is_set():
            alert_flag.set()

    cap.release()
    if stop_monitoring.is_set():
        print("❌ Webcam monitoring stopped due to Block action.")

@app.route("/last_detection", methods=["GET"])
def get_last_detection():
    return jsonify(last_detection)

def check_alert():
    if alert_flag.is_set():
        show_alert_popup()

timer = QTimer()
timer.timeout.connect(check_alert)
timer.start(500)

threading.Thread(target=monitor_webcam, daemon=True).start()
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000), daemon=True).start()

app_qt.exec_()
