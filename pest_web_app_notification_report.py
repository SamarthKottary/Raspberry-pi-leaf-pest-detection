import os
import cv2
import time
import numpy as np
import base64
import datetime
import threading
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from flask import Flask, request, render_template_string, redirect, Response

# --- 🔧 CONFIGURATION (FILL THESE) ---
# 1. TELEGRAM SETTINGS
TELEGRAM_BOT_TOKEN = "8542050953:AAHx-mt8RqhvkfiFKoUT9M_3QZl0y1A_PBE"  # Get from @BotFather
TELEGRAM_CHAT_ID = "1119772887"      # Get from @userinfobot

# 2. EMAIL SETTINGS (For Report Feature)
# Note: For Gmail, use an "App Password" (https://myaccount.google.com/apppasswords)
EMAIL_SENDER = "samarthkottary@gmail.com"
EMAIL_PASSWORD = "qbxn hbom cont vpdv"

# 3. SYSTEM SETTINGS
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
PEST_MIN_AREA = 100
PEST_MAX_AREA = 5000
SERVER_CAMERA_INDEX = 1  # 0 for Laptop/Pi Camera
NOTIFICATION_COOLDOWN = 60 # Seconds between auto-alerts

# --- SETUP ---
SAVE_DIR = "detected_pests"
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# --- GLOBAL STATE ---
last_frame = None
last_notification_time = 0
current_analysis = {} # Stores data for the report (image path, count, etc.)

# --- HTML TEMPLATE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌿 Smart Crop - Pest Lab</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f0f2f5; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; text-align: center; margin-bottom: 30px; }
        
        .controls { text-align: center; margin-bottom: 20px; display: flex; justify-content: center; gap: 15px; flex-wrap: wrap; }
        .btn { display: inline-block; padding: 12px 24px; cursor: pointer; color: white; border-radius: 5px; font-weight: bold; border: none; font-size: 16px; text-decoration: none; transition: opacity 0.3s; }
        .btn:hover { opacity: 0.8; }
        .btn-upload { background: #3498db; }
        .btn-stream { background: #e67e22; }
        .btn-mobile { background: #8e44ad; }
        .btn-snapshot { background: #27ae60; }
        .btn-email { background: #c0392b; width: 100%; margin-top: 10px; }
        
        input[type="file"] { display: none; }
        
        #stream-section { display: none; text-align: center; margin-bottom: 20px; background: #000; padding: 10px; border-radius: 8px; }
        #video-stream { width: 100%; max-width: 640px; height: auto; border: 2px solid #333; }

        .results-container { display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; margin-top: 30px; }
        .image-box { flex: 1; min-width: 300px; text-align: center; border: 1px solid #ddd; padding: 10px; border-radius: 8px; }
        .image-box img { max-width: 100%; height: auto; border-radius: 4px; }
        
        .stats { background: #fff3cd; color: #856404; padding: 15px; border-radius: 6px; text-align: center; margin-top: 20px; font-size: 1.2em; font-weight: bold; border: 1px solid #ffeeba; }
        .stats.clean { background: #d4edda; color: #155724; border-color: #c3e6cb; }
        .alert-msg { color: #2980b9; font-size: 0.8em; margin-top: 5px; font-weight: normal; }

        /* Report Section */
        .report-section { margin-top: 30px; padding: 20px; background: #ecf0f1; border-radius: 8px; border: 1px solid #bdc3c7; }
        .report-input { width: 100%; padding: 10px; margin: 5px 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌿 Smart Crop Pest Detection</h1>
        
        <div class="controls">
            <button onclick="toggleStream()" class="btn btn-stream">📡 Live Monitor</button>
            <label for="mobile-camera" class="btn btn-mobile">📱 Mobile Cam</label>
            <label for="file-upload" class="btn btn-upload">📂 Upload File</label>
        </div>

        <div id="stream-section">
            <h3 style="color: white;">Live Feed</h3>
            <img id="video-stream" src="">
            <br><br>
            <div style="display: flex; justify-content: center; gap: 10px;">
                <button onclick="stopStream()" class="btn btn-upload" style="background: #e74c3c;">🛑 Stop Stream</button>
                <button onclick="captureSnapshot()" class="btn btn-snapshot">📸 Capture Snapshot</button>
            </div>
        </div>

        <form method="POST" enctype="multipart/form-data" id="upload-form">
            <input id="file-upload" type="file" name="file" accept=".jpg,.jpeg,.png" onchange="this.form.submit()">
        </form>

        <form method="POST" enctype="multipart/form-data" id="mobile-form">
            <input id="mobile-camera" type="file" name="file" accept="image/*" capture="environment" onchange="this.form.submit()">
        </form>

        <form method="POST" id="snapshot-form">
            <input type="hidden" name="stream_capture" value="true">
        </form>

        {% if processed_image %}
        <div class="{{ 'stats' if pest_count > 0 else 'stats clean' }}">
            {% if pest_count > 0 %}
                ⚠️ DETECTED: {{ pest_count }} Anomalies
                <div class="alert-msg">Telegram Alert Sent Automatically 📲</div>
            {% else %}
                ✅ HEALTHY: No Pests Detected
            {% endif %}
        </div>

        <div class="results-container">
            <div class="image-box">
                <h3>Original</h3>
                <img src="data:image/jpeg;base64,{{ original_image }}" alt="Original">
            </div>
            <div class="image-box">
                <h3>Analysis</h3>
                <img src="data:image/jpeg;base64,{{ processed_image }}" alt="Processed">
            </div>
        </div>

        <!-- Report Section -->
        <div class="report-section">
            <h3>📝 Send Detailed Report</h3>
            <p>Generate a full analysis report and send it to an expert/manager.</p>
            <form method="POST" action="/send_report">
                <input type="email" name="email_recipient" class="report-input" placeholder="Enter Email Address..." required>
                <button type="submit" class="btn btn-email">📧 Send Analysis via Email</button>
            </form>
            {% if report_status %}
                <p style="color: green; font-weight: bold; margin-top: 10px;">{{ report_status }}</p>
            {% endif %}
        </div>
        {% endif %}
    </div>

    <script>
        function toggleStream() {
            document.getElementById('stream-section').style.display = 'block';
            document.getElementById('video-stream').src = "{{ url_for('video_feed') }}";
        }
        function stopStream() {
            document.getElementById('video-stream').src = "";
            document.getElementById('stream-section').style.display = 'none';
        }
        function captureSnapshot() {
            document.getElementById('snapshot-form').submit();
        }
    </script>
</body>
</html>
"""

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- 📧 EMAIL LOGIC ---
def send_email(recipient, image_path, count, status):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = recipient
    msg['Subject'] = f"🚨 Pest Detection Report - {datetime.datetime.now().strftime('%Y-%m-%d')}"

    # Analysis Text
    severity = "LOW" if count < 3 else "HIGH"
    body = f"""
    SMART CROP MONITORING REPORT
    ---------------------------------
    Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    Status: {status}
    Pest Count: {count}
    Severity: {severity}
    
    RECOMMENDATION:
    {'No action needed. Plant looks healthy.' if count == 0 else 'Immediate inspection recommended. Potential infestation detected.'}
    
    ---------------------------------
    Auto-generated by Raspberry Pi Smart Crop System
    """
    msg.attach(MIMEText(body, 'plain'))

    # Attach Image
    if os.path.exists(image_path):
        with open(image_path, 'rb') as f:
            img_data = f.read()
            image = MIMEImage(img_data, name=os.path.basename(image_path))
            msg.attach(image)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, recipient, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

# --- 📲 TELEGRAM LOGIC ---
def send_telegram_alert(image_path, count):
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        with open(image_path, "rb") as img_file:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": f"⚠️ <b>PEST DETECTED!</b>\nCount: {count}\nTime: {datetime.datetime.now().strftime('%H:%M:%S')}",
                "parse_mode": "HTML"
            }
            files = {"photo": img_file}
            requests.post(url, data=payload, files=files)
            print("✅ Telegram Alert Sent")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

# --- 🧠 ANALYSIS LOGIC ---
def save_and_alert(image, count):
    global last_notification_time, current_analysis
    
    # Save Image with Timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{SAVE_DIR}/pest_{timestamp}.jpg"
    cv2.imwrite(filename, image)
    
    # Update Global State for Reporting
    current_analysis = {
        "path": filename,
        "count": count,
        "status": "INFECTED" if count > 0 else "HEALTHY"
    }

    # Auto-Notification (Throttled)
    current_time = time.time()
    if count > 0 and (current_time - last_notification_time > NOTIFICATION_COOLDOWN):
        t = threading.Thread(target=send_telegram_alert, args=(filename, count))
        t.start()
        last_notification_time = current_time

def analyze_pest_logic(frame, auto_save=False):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # Adjust Green Mask (Hue 35-85 is generic green)
    lower_green = np.array([35, 40, 40])
    upper_green = np.array([85, 255, 255])
    
    mask_green = cv2.inRange(hsv, lower_green, upper_green)
    mask_not_green = cv2.bitwise_not(mask_green)
    
    kernel = np.ones((5,5), np.uint8)
    mask_clean = cv2.morphologyEx(mask_not_green, cv2.MORPH_OPEN, kernel)
    
    contours, _ = cv2.findContours(mask_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    pest_count = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if PEST_MIN_AREA < area < PEST_MAX_AREA:
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
            cv2.putText(frame, "PEST", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            pest_count += 1
    
    # Always update current analysis state on manual triggers
    if auto_save: 
        save_and_alert(frame, pest_count)
            
    return frame, pest_count

def encode_results(original, processed):
    _, buffer_orig = cv2.imencode('.jpg', original)
    _, buffer_proc = cv2.imencode('.jpg', processed)
    return base64.b64encode(buffer_orig).decode('utf-8'), base64.b64encode(buffer_proc).decode('utf-8')

# --- 🎥 VIDEO STREAMING ---
def gen_frames():
    global last_frame
    cap = cv2.VideoCapture(SERVER_CAMERA_INDEX)
    time.sleep(0.5)
    if not cap.isOpened(): return

    while True:
        success, frame = cap.read()
        if not success: break
        last_frame = frame.copy()
        
        # Auto-save=True means live monitoring triggers alerts
        processed_frame, count = analyze_pest_logic(frame, auto_save=True)
        
        status_color = (0, 255, 0) if count == 0 else (0, 0, 255)
        cv2.putText(processed_frame, f"Pests: {count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
        
        ret, buffer = cv2.imencode('.jpg', processed_frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    cap.release()

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# --- 📨 REPORT ROUTE ---
@app.route('/send_report', methods=['POST'])
def send_report():
    recipient = request.form.get('email_recipient')
    
    # Check if we have analysis data to send
    if not current_analysis or 'path' not in current_analysis:
        return "Error: No analysis available to report. Please capture an image first."
    
    success = send_email(recipient, current_analysis['path'], current_analysis['count'], current_analysis['status'])
    
    # Re-render the page with a success/fail message
    # Note: In a real app, we'd restart the session or handle state better, 
    # but for this demo, we just pass a flag to the template.
    return render_template_string(HTML_TEMPLATE, 
                                  report_status="✅ Email Report Sent!" if success else "❌ Failed to send Email",
                                  # We need to re-encode images to show them again
                                  # (Ideally, you'd cache the base64 strings, but this is simpler)
                                  processed_image="", # Placeholder to hide images or you can implement full state
                                  pest_count=current_analysis['count'])

@app.route('/', methods=['GET', 'POST'])
def index():
    global current_analysis
    if request.method == 'POST':
        frame = None
        if 'stream_capture' in request.form and last_frame is not None:
            frame = last_frame.copy()
        elif 'file' in request.files:
            file = request.files['file']
            if file.filename != '' and allowed_file(file.filename):
                file_bytes = file.read()
                nparr = np.frombuffer(file_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is not None:
            original = frame.copy()
            # Manual trigger: always save/alert
            processed_frame, count = analyze_pest_logic(frame, auto_save=True)
            orig_b64, proc_b64 = encode_results(original, processed_frame)
            
            return render_template_string(HTML_TEMPLATE, 
                                        original_image=orig_b64, 
                                        processed_image=proc_b64, 
                                        pest_count=count)
            
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    print("🌍 Starting Web Server...")
    app.run(debug=True, port=5000, host='0.0.0.0')