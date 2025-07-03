from flask import Flask, request, jsonify
import subprocess
import threading
import os
import json
import datetime
import time
import pytz

app = Flask(__name__)

RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

active_recordings = {}  # {recording_id: {"process": Popen, "filepath": str, "metadata": dict}}

# Load channels.json
with open("channels.json", "r") as f:
    channels = {c["id"]: c for c in json.load(f)}

UK_TZ = pytz.timezone("Europe/London")

def safe_filename(s):
    import re
    return re.sub(r"[^\w\-_. ]", "_", s)

def parse_time(timestr):
    if not timestr:
        return None
    try:
        return UK_TZ.localize(datetime.datetime.fromisoformat(timestr))
    except Exception:
        return None

def start_recording(recording_id, stream_url, metadata):
    start_time_str = metadata.get("start", datetime.datetime.now().isoformat())
    title = safe_filename(metadata.get("title", "unknown"))
    channel = safe_filename(metadata.get("channel", "unknown"))
    filename = f"{start_time_str}_{channel}_{title}.mp4"
    filepath = os.path.join(RECORDINGS_DIR, filename)

    meta_path = filepath + ".json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", stream_url,
        "-c", "copy",
        "-f", "mp4",
        filepath
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    active_recordings[recording_id] = {"process": proc, "filepath": filepath, "metadata": metadata}
    print(f"Started recording {recording_id} -> {filepath}")
    return filepath

def stop_recording(recording_id):
    rec = active_recordings.get(recording_id)
    if not rec:
        return False
    proc = rec["process"]
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    del active_recordings[recording_id]
    print(f"Stopped recording {recording_id}")
    return True

scheduler_lock = threading.Lock()
scheduled_recordings = {}  # recording_id: {"start": datetime, "stop": datetime, "metadata": dict, "stream_url": str}

def scheduler_loop():
    while True:
        now = datetime.datetime.now(UK_TZ)

        to_start = []
        to_stop = []

        with scheduler_lock:
            for rid, info in list(scheduled_recordings.items()):
                if rid in active_recordings:
                    # Check if it's time to stop
                    if info["stop"] and now >= info["stop"]:
                        to_stop.append(rid)
                else:
                    # Check if it's time to start
                    if now >= info["start"]:
                        to_start.append(rid)

            for rid in to_start:
                info = scheduled_recordings[rid]
                start_recording(rid, info["stream_url"], info["metadata"])

            for rid in to_stop:
                stop_recording(rid)
                scheduled_recordings.pop(rid, None)

        time.sleep(30)

@app.route("/api/recordings/start", methods=["POST"])
def api_start_recording():
    data = request.json
    channel_id = data.get("channel_id")
    title = data.get("title", "")
    description = data.get("description", "")
    start = data.get("start")
    stop = data.get("stop")

    if not channel_id or channel_id not in channels:
        return jsonify({"error": "Invalid channel_id"}), 400

    stream_url = channels[channel_id]["stream"]
    if not stream_url:
        return jsonify({"error": "Stream URL not found for channel"}), 400

    recording_id = f"{channel_id}_{int(datetime.datetime.now().timestamp())}"
    start_dt = parse_time(start) if start else datetime.datetime.now(UK_TZ)
    stop_dt = parse_time(stop) if stop else None

    metadata = {
        "channel": channel_id,
        "title": title,
        "description": description,
        "start": start_dt.isoformat(),
        "stop": stop_dt.isoformat() if stop_dt else None
    }

    now = datetime.datetime.now(UK_TZ)

    if start_dt > now:
        with scheduler_lock:
            scheduled_recordings[recording_id] = {
                "start": start_dt,
                "stop": stop_dt,
                "metadata": metadata,
                "stream_url": stream_url
            }
        return jsonify({"recording_id": recording_id, "status": "scheduled"})
    else:
        filepath = start_recording(recording_id, stream_url, metadata)
        return jsonify({"recording_id": recording_id, "filepath": filepath, "status": "recording"})

@app.route("/api/recordings/stop", methods=["POST"])
def api_stop_recording():
    data = request.json
    recording_id = data.get("recording_id")
    if not recording_id:
        return jsonify({"error": "Missing recording_id"}), 400
    success = stop_recording(recording_id)
    if not success:
        return jsonify({"error": "Recording not found"}), 404
    return jsonify({"status": "stopped", "recording_id": recording_id})

@app.route("/api/recordings", methods=["GET"])
def api_list_recordings():
    recs = []
    for rec_id, rec in active_recordings.items():
        recs.append({
            "recording_id": rec_id,
            "filepath": rec["filepath"],
            "metadata": rec["metadata"]
        })
    return jsonify(recs)

@app.route("/api/recordings/scheduled", methods=["GET"])
def api_list_scheduled():
    with scheduler_lock:
        return jsonify([
            {
                "recording_id": rid,
                "start": info["start"].isoformat(),
                "stop": info["stop"].isoformat() if info["stop"] else None,
                "metadata": info["metadata"]
            }
            for rid, info in scheduled_recordings.items()
        ])

if __name__ == "__main__":
    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    app.run(host="0.0.0.0", port=8080)
