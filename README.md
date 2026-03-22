# Crypto Eye

**Crypto Eye** is a **Python-based facial recognition security application** designed to protect workspace privacy in real time. If an unauthorized person is detected viewing the screen while the admin is working, the app instantly **locks the screen** and displays a **security alert message**.

---

## Features
- Real-time facial recognition using a webcam
- Instantly locks the screen if unauthorized access is detected
- Displays a security alert message to notify the admin
- Lightweight and easy-to-use interface

---

## Tech Stack / Topics
- **Languages & Frameworks:** Python, Flask, PyQt5
- **Libraries & Tools:** OpenCV (cv2), face-recognition, OS module
- **Functionality:** Real-time monitoring, facial recognition, screen locking

---

## Screenshots / Demo
> Replace `path_to_image` with actual image paths from your repo

![Login Screen](path_to_image/login.png)  
![Unauthorized Detection Alert](path_to_image/alert.png)  
![Admin Dashboard](path_to_image/dashboard.png)

---

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/crypto-eye.git
cd crypto-eye
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python crypto_eye.py
```