import os
import cv2
import time
import numpy as np
import base64
from flask import Flask, request, render_template_string, redirect, Response

# --- CONFIGURATION ---
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
PEST_MIN_AREA = 100
PEST_MAX_AREA = 5000
SERVER_CAMERA_INDEX = 1  # Change to 1 or 2 if using external USB cam on Laptop

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# Global variables for streaming
camera = None
last_frame = None  # Stores the latest clean frame for snapshotting

# --- HTML & JAVASCRIPT TEMPLATE ---
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
        
        /* Controls */
        .controls { text-align: center; margin-bottom: 20px; display: flex; justify-content: center; gap: 15px; flex-wrap: wrap; }
        
        .btn { display: inline-block; padding: 12px 24px; cursor: pointer; color: white; border-radius: 5px; font-weight: bold; transition: background 0.3s; border: none; font-size: 16px; text-decoration: none; }
        
        .btn-upload { background: #3498db; }
        .btn-upload:hover { background: #2980b9; }
        
        .btn-stream { background: #e67e22; }
        .btn-stream:hover { background: #d35400; }
        
        .btn-mobile { background: #8e44ad; }
        .btn-mobile:hover { background: #732d91; }

        /* Snapshot Button Style */
        .btn-snapshot { background: #27ae60; margin-left: 10px; }
        .btn-snapshot:hover { background: #219150; }

        input[type="file"] { display: none; }
        
        /* Stream Container */
        #stream-section { display: none; text-align: center; margin-bottom: 20px; background: #000; padding: 10px; border-radius: 8px; }
        #video-stream { width: 100%; max-width: 640px; height: auto; border-radius: 4px; border: 2px solid #333; }

        /* Results */
        .results-container { display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; margin-top: 30px; }
        .image-box { flex: 1; min-width: 300px; text-align: center; border: 1px solid #ddd; padding: 10px; border-radius: 8px; }
        .image-box img { max-width: 100%; height: auto; border-radius: 4px; }
        .image-box h3 { color: #555; margin: 10px 0; }
        
        .stats { background: #fff3cd; color: #856404; padding: 15px; border-radius: 6px; text-align: center; margin-top: 20px; font-size: 1.2em; font-weight: bold; border: 1px solid #ffeeba; }
        .stats.clean { background: #d4edda; color: #155724; border-color: #c3e6cb; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌿 Smart Crop Pest Detection Lab</h1>
        
        <!-- Action Buttons -->
        <div class="controls">
            <!-- 1. Live Stream (Server Cam) -->
            <button onclick="toggleStream()" class="btn btn-stream">📡 Live Stream</button>
            
            <!-- 2. Mobile Native Camera -->
            <label for="mobile-camera" class="btn btn-mobile">📱 Mobile Cam</label>

            <!-- 3. Upload File -->
            <label for="file-upload" class="btn btn-upload">📂 Upload File</label>
        </div>

        <!-- Live Video Stream -->
        <div id="stream-section">
            <h3 style="color: white;">Live Server Feed (Real-Time Detection)</h3>
            <img id="video-stream" src="">
            <br><br>
            <div style="display: flex; justify-content: center; gap: 10px;">
                <button onclick="stopStream()" class="btn btn-upload" style="background: #c0392b;">🛑 Stop Stream</button>
                
                <!-- NEW Snapshot Button -->
                <button onclick="captureSnapshot()" class="btn btn-snapshot">📸 Capture Snapshot</button>
            </div>
        </div>

        <!-- Forms -->
        <form method="POST" enctype="multipart/form-data" id="upload-form">
            <input id="file-upload" type="file" name="file" accept=".jpg,.jpeg,.png" onchange="this.form.submit()">
        </form>

        <form method="POST" enctype="multipart/form-data" id="mobile-form">
            <input id="mobile-camera" type="file" name="file" accept="image/*" capture="environment" onchange="this.form.submit()">
        </form>

        <!-- Hidden Form for Snapshot -->
        <form method="POST" id="snapshot-form">
            <input type="hidden" name="stream_capture" value="true">
        </form>

        {% if processed_image %}
        <div class="{{ 'stats' if pest_count > 0 else 'stats clean' }}">
            {% if pest_count > 0 %}
                ⚠️ DETECTED: {{ pest_count }} Potential Anomalies
            {% else %}
                ✅ HEALTHY: No Pests Detected
            {% endif %}
        </div>

        <div class="results-container">
            <div class="image-box">
                <h3>Original Image</h3>
                <img src="data:image/jpeg;base64,{{ original_image }}" alt="Original">
            </div>
            <div class="image-box">
                <h3>Analysis Result</h3>
                <img src="data:image/jpeg;base64,{{ processed_image }}" alt="Processed">
            </div>
        </div>
        {% endif %}
    </div>

    <script>
        function toggleStream() {
            const streamSection = document.getElementById('stream-section');
            const streamImg = document.getElementById('video-stream');
            
            // Set the source to the Flask route to start streaming
            streamImg.src = "{{ url_for('video_feed') }}";
            streamSection.style.display = 'block';
        }

        function stopStream() {
            const streamSection = document.getElementById('stream-section');
            const streamImg = document.getElementById('video-stream');
            
            // Clear source to stop bandwidth usage
            streamImg.src = "";
            streamSection.style.display = 'none';
        }

        function captureSnapshot() {
            // Submit the hidden form to trigger server-side capture from stream
            document.getElementById('snapshot-form').submit();
        }
    </script>
</body>
</html>
"""

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- CORE LOGIC ---
def analyze_pest_logic(frame):
    """
    Core processing function.
    Returns: (processed_frame, pest_count)
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # "Healthy Green" Range
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
            cv2.putText(frame, "PEST", (x, y - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            pest_count += 1
            
    return frame, pest_count

def encode_results(original, processed):
    _, buffer_orig = cv2.imencode('.jpg', original)
    _, buffer_proc = cv2.imencode('.jpg', processed)
    
    orig_b64 = base64.b64encode(buffer_orig).decode('utf-8')
    proc_b64 = base64.b64encode(buffer_proc).decode('utf-8')
    return orig_b64, proc_b64

# --- STREAMING GENERATOR ---
def gen_frames():
    """Generates a continuous stream of JPEG frames with pest detection boxes."""
    global last_frame
    cap = cv2.VideoCapture(SERVER_CAMERA_INDEX)
    
    # Camera Warmup
    time.sleep(0.5)
    
    if not cap.isOpened():
        print("Error: Could not open server camera for streaming.")
        return

    while True:
        success, frame = cap.read()
        if not success:
            break
        
        # SAVE CLEAN FRAME FOR SNAPSHOT
        # This ensures we don't get "double boxes" when we capture
        last_frame = frame.copy()

        # Run detection on the live frame!
        processed_frame, count = analyze_pest_logic(frame)
        
        # Add a timestamp or status text
        status_color = (0, 255, 0) if count == 0 else (0, 0, 255)
        cv2.putText(processed_frame, f"Pests Detected: {count}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)

        # Encode to JPEG
        ret, buffer = cv2.imencode('.jpg', processed_frame)
        frame_bytes = buffer.tobytes()
        
        # Yield the frame in Multipart format (Standard for IP Cams)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    cap.release()

@app.route('/video_feed')
def video_feed():
    """Route that returns the streaming response"""
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        
        # --- CASE 1: SNAPSHOT FROM LIVE STREAM ---
        if 'stream_capture' in request.form:
            if last_frame is not None:
                # Use the cached clean frame from the live stream
                original = last_frame.copy()
                processed_frame, count = analyze_pest_logic(last_frame.copy())
                orig_b64, proc_b64 = encode_results(original, processed_frame)
                
                return render_template_string(HTML_TEMPLATE, 
                                            original_image=orig_b64, 
                                            processed_image=proc_b64, 
                                            pest_count=count)
            else:
                return "Error: Stream not active or no frame available to capture."

        # --- CASE 2: FILE UPLOAD ---
        if 'file' in request.files:
            file = request.files['file']
            if file.filename != '' and allowed_file(file.filename):
                file_bytes = file.read()
                nparr = np.frombuffer(file_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                original = frame.copy()
                processed_frame, count = analyze_pest_logic(frame)
                orig_b64, proc_b64 = encode_results(original, processed_frame)
                
                return render_template_string(HTML_TEMPLATE, 
                                            original_image=orig_b64, 
                                            processed_image=proc_b64, 
                                            pest_count=count)
            
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    print("🌍 Starting Web Server...")
    app.run(debug=True, port=5000, host='0.0.0.0')