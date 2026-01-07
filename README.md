# Leaf Pest Detection System using Raspberry Pi

A smart farming project designed to monitor plant health automatically. This system uses a Raspberry Pi 4 to detect pests on leaves using a camera and tracks environmental conditions like temperature, humidity, and soil moisture.

## Project Overview

This project helps you monitor your crops or home plants remotely. It hosts a local website where you can view a live video feed of your plant. The system uses **Computer Vision (OpenCV)** to analyze the video and identify pests or spots on leaves. It also reads data from physical sensors to determine if the plant needs water or if the environment is too hot. If pests are detected, the system sends an email report with a photo to the user.

## Technologies Used

* **Hardware:** Raspberry Pi 4, Pi Camera Module, DHT11 Sensor, Capacitive Soil Moisture Sensor.
* **Programming Language:** Python 3.
* **Web Framework:** Flask (for the dashboard and video streaming).
* **Image Processing:** OpenCV (cv2) and NumPy.
* **Communication:** SMTP (for sending Email alerts).

## Key Features

* **Live Monitoring:** Stream real-time video of your plant to any phone or laptop on the WiFi.
* **Automatic Pest Detection:** Detects bugs and disease spots on leaves using color-based image processing.
* **Environmental Sensing:** Continuously tracks Temperature, Humidity (DHT11), and Soil Moisture.
* **Email Alerts:** Automatically sends a status report with an attached photo if pests are found.
* **Plug-and-Play:** Designed to auto-connect to WiFi and start the monitoring software immediately upon powering on.

## Hardware Required

| Component | Function | Connection |
| --- | --- | --- |
| **Raspberry Pi 4** | Main Controller | N/A |
| **Pi Camera** | Video & Pest Detection | CSI Port |
| **DHT11 Sensor** | Temperature & Humidity | GPIO 4 (Physical Pin 7) |
| **Soil Sensor** | Moisture Detection | GPIO 14 (Physical Pin 8) |

### Wiring Guide

* **DHT11 Data Pin:** Connect to GPIO 4
* **Soil Sensor (DO Pin):** Connect to GPIO 14
* **VCC:** Connect to 3.3V (Physical Pin 1)
* **GND:** Connect to Ground (Physical Pin 6)

## Installation

1. **Clone this Repository**
```bash
git clone https://github.com/SamarthKottary/Raspberry-pi-leaf-pest-detection.git
cd Raspberry-pi-leaf-pest-detection

```


2. **Set up Python Environment**
```bash
python3 -m venv venv
source venv/bin/activate

```


3. **Install Dependencies**
```bash
pip install -r requirements.txt

```


4. **Configuration**
Open `app.py` and update your email details so the Pi can send alerts:
```python
EMAIL_SENDER = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"  # App Password from Google Security settings
ADMIN_EMAIL = "admin_email@gmail.com"

```



## Usage

### Manual Start (For Testing)

To run the app manually:

```bash
python3 app.py

```

### Auto-Start (For Deployment)

To make the system start automatically when you plug in the Raspberry Pi:

1. Create a service file: `sudo nano /etc/systemd/system/smartcrop.service`
2. Enable the service:
```bash
sudo systemctl enable smartcrop.service
sudo systemctl start smartcrop.service

```



### How to Access

* **On your Phone/PC:** Open a browser and type `http://<raspberry-pi-ip>:5000`
* **Auto-Discovery:** When the Pi starts, it will email you its IP address automatically if configured.
