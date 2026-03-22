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

admin_dir = "dataset/admin"
admin_encodings = []

if not os.path.exists(admin_dir):
    raise FileNotFoundError(f"❌ Admin folder not found: {admin_dir}")

for img_name in os.listdir(admin_dir):
    path = os.path.join(admin_dir, img_name)
    try:
        image = face_recognition.load_image_file(path)
        encs = face_recognition.face_encodings(image)
        if encs:
            admin_encodings.append(encs[0])
    except Exception as e:
        print(f"⚠️ Could not process {img_name}: {e}")

if len(admin_encodings) == 0:
    raise ValueError("❌ No admin faces found in the folder!")

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
    msg.setText("Bro Someone else watching you!\n\nAllow the user to watch ?")
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    msg.setWindowModality(Qt.ApplicationModal)
    msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
    choice = msg.exec_()

    if choice == QMessageBox.Yes:
        print("✅ Access Allowed")

    else:
        print("❌ Access Blocked")
        stop_monitoring.set()

    alert_flag.clear()

def monitor_webcam():
    global last_detection
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Cannot open webcam")
        return

    while not stop_monitoring.is_set():
        ret, frame = cap.read()
        if not ret:
            break

        small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        alert_triggered = False

        for enc in face_encodings:
            distances = face_recognition.face_distance(admin_encodings, enc)
            if len(distances) > 0 and np.min(distances) < threshold:
                label = "Admin"
            else:
                label = "Others"
                alert_triggered = True

            last_detection = {
                "label": label,
                "distance": float(np.min(distances)) if len(distances) > 0 else None
            }

            print(f"📸 Detection: {last_detection}")

        if (alert_triggered or len(face_encodings) > 1) and not alert_flag.is_set():
            alert_flag.set()

    cap.release()
    if stop_monitoring.is_set():
        print("❌ Webcam monitoring stopped due to Block action.")
        sys.exit(0)

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