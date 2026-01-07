import os
import cv2
import time
import numpy as np
import base64
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from flask import Flask, request, render_template_string, redirect, Response, url_for, flash

# --- 🔧 CONFIGURATION ---
EMAIL_SENDER = "samarthkottary@gmail.com"
EMAIL_PASSWORD = "qbxn hbom cont vpdv"

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
PEST_MIN_AREA = 100
PEST_MAX_AREA = 5000
SAVE_DIR = "detected_pests"

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# --- GLOBAL STATE ---
last_frame = None
current_analysis = {} 
active_camera_source = 0 
is_gstreamer = False

# --- 🛠️ ROBUST CAMERA FINDER ---
def find_working_camera():
    """Tries 4 different methods to force the Pi Camera to work."""
    global is_gstreamer
    
    # --- METHOD 1: V4L2 with MJPEG (Most Reliable for Legacy Mode) ---
    print("🔍 Attempt 1: Standard V4L2 with MJPEG...")
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG')) # Force MJPEG
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None and frame.size > 0:
            print("✅ Success! Using Index 0 (MJPEG Mode)")
            cap.release()
            is_gstreamer = False
            return 0
    cap.release()

    # --- METHOD 2: Standard V4L2 Default (Backup) ---
    print("🔍 Attempt 2: Standard V4L2 Default...")
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None and frame.size > 0:
            print("✅ Success! Using Index 0 (Default Mode)")
            cap.release()
            is_gstreamer = False
            return 0
    cap.release()

    # --- METHOD 3: Libcamera GStreamer (For New OS) ---
    print("🔍 Attempt 3: Libcamera GStreamer...")
    gst_pipe = (
        "libcamerasrc ! video/x-raw, width=640, height=480, framerate=30/1 ! "
        "videoconvert ! video/x-raw, format=BGR ! appsink"
    )
    try:
        cap = cv2.VideoCapture(gst_pipe, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                print("✅ Success! Using Libcamera GStreamer")
                cap.release()
                is_gstreamer = True
                return gst_pipe
    except:
        pass

    # --- METHOD 4: V4L2 GStreamer (Last Resort) ---
    print("🔍 Attempt 4: V4L2Src GStreamer...")
    gst_v4l2 = (
        "v4l2src device=/dev/video0 ! video/x-raw, width=640, height=480 ! "
        "videoconvert ! video/x-raw, format=BGR ! appsink"
    )
    try:
        cap = cv2.VideoCapture(gst_v4l2, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                print("✅ Success! Using V4L2 GStreamer")
                cap.release()
                is_gstreamer = True
                return gst_v4l2
    except:
        pass

    print("❌ CRITICAL ERROR: Could not read from camera using any method.")
    return 0

# Run detection once on startup
active_camera_source = find_working_camera()

# --- HTML TEMPLATE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌿 Pi Smart Crop Monitor</title>
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
        .btn-stop { background: #c0392b; }
        .btn-email { background: #e74c3c; width: 100%; margin-top: 5px; }
        
        input[type="file"] { display: none; }
        
        #stream-section { display: none; text-align: center; margin-bottom: 20px; background: #000; padding: 10px; border-radius: 8px; }
        #video-stream { width: 100%; max-width: 640px; height: auto; border: 2px solid #333; }

        .results-container { display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; margin-top: 30px; }
        .image-box { flex: 1; min-width: 300px; text-align: center; border: 1px solid #ddd; padding: 10px; border-radius: 8px; }
        .image-box img { max-width: 100%; height: auto; border-radius: 4px; }
        
        .stats { background: #fff3cd; color: #856404; padding: 15px; border-radius: 6px; text-align: center; margin-top: 20px; font-size: 1.2em; font-weight: bold; border: 1px solid #ffeeba; }
        .stats.clean { background: #d4edda; color: #155724; border-color: #c3e6cb; }

        .actions-section { margin-top: 30px; display: flex; justify-content: center; flex-wrap: wrap; }
        .action-card { flex: 1; max-width: 500px; padding: 20px; background: #ecf0f1; border-radius: 8px; border: 1px solid #bdc3c7; }
        .report-input { width: 100%; padding: 10px; margin: 5px 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
        
        .flashes { list-style: none; padding: 0; margin-bottom: 20px; }
        .flash-msg { padding: 15px; border-radius: 5px; margin-bottom: 10px; font-weight: bold; text-align: center; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
        .info { background: #cce5ff; color: #004085; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌿 Pi Smart Crop Monitor</h1>
        
        <!-- Flash Messages -->
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            <div class="flashes">
            {% for category, message in messages %}
              <div class="flash-msg {{ category }}">{{ message }}</div>
            {% endfor %}
            </div>
          {% endif %}
        {% endwith %}
        
        <div class="controls">
            <button onclick="toggleStream()" class="btn btn-stream">📡 Live Monitor</button>
            <label for="mobile-camera" class="btn btn-mobile">📱 Mobile Cam</label>
            <label for="file-upload" class="btn btn-upload">📂 Upload File</label>
        </div>

        <div id="stream-section">
            <h3 style="color: white;">Pi Camera Feed</h3>
            <img id="video-stream" src="">
            <br><br>
            <div style="display: flex; justify-content: center; gap: 10px;">
                <button onclick="stopStream()" class="btn btn-stop">🛑 Stop Stream</button>
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

        <div class="actions-section">
            <div class="action-card">
                <h3>📧 Email Report</h3>
                <p>Send full analysis report with image.</p>
                <form method="POST" action="/send_report">
                    <input type="email" name="email_recipient" class="report-input" placeholder="Enter Email..." required>
                    <button type="submit" class="btn btn-email">Send Mail</button>
                </form>
            </div>
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

def send_email(recipient, image_path, count, status):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = recipient
    msg['Subject'] = f"🌿 Crop Health Report - {datetime.datetime.now().strftime('%Y-%m-%d')}"

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if count == 0:
        status_color = "#27ae60" 
        status_text = "HEALTHY"
        severity = "NONE"
        observation = "No visible pests were detected. The foliage appears clean."
        recommendations = """
            <li><strong>Monitor:</strong> Continue regular monitoring.</li>
            <li><strong>Maintenance:</strong> Ensure optimal watering/lighting.</li>
        """
    else:
        status_color = "#c0392b" 
        status_text = "INFECTED"
        severity = "HIGH" if count >= 5 else "LOW"
        observation = f"Detected <strong>{count} anomalies</strong> on the leaves."
        recommendations = """
            <li><strong>ISOLATE:</strong> Separate this plant immediately.</li>
            <li><strong>INSPECT:</strong> Check underside of leaves.</li>
            <li><strong>TREAT:</strong> Apply Neem Oil or suitable pesticide.</li>
        """

    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; border: 1px solid #ddd; padding: 20px; }}
            .status-box {{ background-color: {status_color}; color: white; padding: 10px; text-align: center; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🌿 Smart Crop Report</h2>
            <div class="status-box">STATUS: {status_text}</div>
            <p><strong>Date:</strong> {timestamp}</p>
            <p><strong>Pest Count:</strong> {count} | <strong>Severity:</strong> {severity}</p>
            <h3>🔍 Observations</h3>
            <p>{observation}</p>
            <h3>🛡️ Recommendations</h3>
            <ul>{recommendations}</ul>
            <p><em>Analyzed image attached.</em></p>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(html_body, 'html'))

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

def update_current_state(image, count, original_img, processed_img):
    global current_analysis
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{SAVE_DIR}/pest_{timestamp}.jpg"
    cv2.imwrite(filename, processed_img)
    
    _, buffer_orig = cv2.imencode('.jpg', original_img)
    _, buffer_proc = cv2.imencode('.jpg', processed_img)
    orig_b64 = base64.b64encode(buffer_orig).decode('utf-8')
    proc_b64 = base64.b64encode(buffer_proc).decode('utf-8')

    current_analysis = {
        "path": filename,
        "count": count,
        "status": "INFECTED" if count > 0 else "HEALTHY",
        "timestamp": timestamp,
        "orig_b64": orig_b64,
        "proc_b64": proc_b64
    }

def analyze_pest_logic(frame, auto_update_state=False):
    original = frame.copy()
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
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
            
    if auto_update_state:
        update_current_state(frame, pest_count, original, frame)
            
    return frame, pest_count

def gen_frames():
    global last_frame
    
    if is_gstreamer:
        cap = cv2.VideoCapture(active_camera_source, cv2.CAP_GSTREAMER)
    else:
        cap = cv2.VideoCapture(active_camera_source, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    time.sleep(0.5)
    
    if not cap.isOpened():
        print("❌ Camera failed to open in stream thread.")
        return

    while True:
        success, frame = cap.read()
        if not success:
            print("❌ Failed to read frame from stream.")
            break
        last_frame = frame.copy()
        processed_frame, count = analyze_pest_logic(frame, auto_update_state=False)
        
        status_color = (0, 255, 0) if count == 0 else (0, 0, 255)
        cv2.putText(processed_frame, f"Live Pests: {count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
        
        ret, buffer = cv2.imencode('.jpg', processed_frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    cap.release()

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/send_report', methods=['POST'])
def send_report():
    recipient = request.form.get('email_recipient')
    
    if not current_analysis:
        flash("No analysis data available! Capture an image first.", "error")
        return redirect(url_for('index'))

    if not recipient:
        flash("Please enter a valid email address.", "error")
        return redirect(url_for('index'))

    success = send_email(recipient, current_analysis.get('path'), current_analysis.get('count', 0), current_analysis.get('status'))

    if success:
        flash(f"✅ Report sent to {recipient}!", "success")
    else:
        flash("❌ Email Failed. Check console/password.", "error")
        
    return redirect(url_for('index'))

@app.route('/', methods=['GET', 'POST'])
def index():
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
            analyze_pest_logic(frame, auto_update_state=True)
            flash("Analysis Complete! Review options below.", "info")
            
    return render_template_string(HTML_TEMPLATE, 
                                  processed_image=current_analysis.get('proc_b64', ''),
                                  original_image=current_analysis.get('orig_b64', ''),
                                  pest_count=current_analysis.get('count', 0))

if __name__ == '__main__':
    print("🌍 Starting Web Server on Pi...")
    app.run(debug=True, port=5000, host='0.0.0.0', use_reloader=False)