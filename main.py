from flask import Flask, request, jsonify
import subprocess
import threading
import os
import json
import datetime
import time
import urllib.request
import xml.etree.ElementTree as ET
import pytz
import ssl
import re

app = Flask(__name__)

RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Active recording processes: {recording_id: {"process": Popen, "filepath": str, "metadata": dict}}
active_recordings = {}

# User scheduled recordings: {recording_id: {"start": datetime, "stop": datetime, "metadata": dict}}
user_scheduled_recordings = {}
scheduler_lock = threading.Lock()

# Load channels.json to get stream URLs and support lookup by number
with open("channels.json", "r") as f:
    channels_list = json.load(f)
channels = {c["id"]: c for c in channels_list}
channels_by_number = {c["number"]: c for c in channels_list}

UK_TZ = pytz.timezone("Europe/London")
EPG_URL = "https://raw.githubusercontent.com/dp247/Freeview-EPG/master/epg.xml"

def safe_filename(s):
    return re.sub(r"[^\w\-_. ]", "_", s)

def parse_time(timestr):
    if not timestr:
        return None
    try:
        timestr = timestr.split()[0]
        naive = datetime.datetime.strptime(timestr, "%Y%m%d%H%M%S")
        return UK_TZ.localize(naive)
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

def fetch_epg():
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(EPG_URL, context=context) as response:
            content = response.read()
        root = ET.fromstring(content)
        epg = {}
        for programme in root.findall("programme"):
            chan_id = programme.get("channel")
            if chan_id not in channels:
                continue
            start = parse_time(programme.get("start"))
            stop = parse_time(programme.get("stop"))
            if not start or not stop:
                continue
            title = programme.findtext("title", "")
            desc = programme.findtext("desc", "")
            epg.setdefault(chan_id, []).append({
                "start": start,
                "stop": stop,
                "title": title,
                "desc": desc
            })
        for chan in epg:
            epg[chan].sort(key=lambda x: x["start"])
        return epg
    except Exception as e:
        print("Error fetching EPG:", e)
        return {}

def get_channel_by_id_or_number(id_or_number):
    # Try id first, then number
    if id_or_number in channels:
        return channels[id_or_number]
    if id_or_number in channels_by_number:
        return channels_by_number[id_or_number]
    return None

def scheduler_loop():
    while True:
        now = datetime.datetime.now(UK_TZ)

        with scheduler_lock:
            # Start scheduled recordings if their start time is within next 60 seconds and not already recording
            for rid, info in list(user_scheduled_recordings.items()):
                if rid in active_recordings:
                    continue  # already recording

                start = info["start"]
                if 0 <= (start - now).total_seconds() < 60:
                    stream_url = info["metadata"].get("stream_url")
                    if not stream_url:
                        print(f"No stream_url for scheduled recording {rid}, skipping")
                        continue
                    start_recording(rid, stream_url, info["metadata"])
                    print(f"Scheduled recording started: {rid}")

            # Stop recordings that have passed their stop time
            to_remove = []
            for rid, info in list(user_scheduled_recordings.items()):
                stop = info["stop"]
                if now >= stop and rid in active_recordings:
                    stop_recording(rid)
                    to_remove.append(rid)

            for rid in to_remove:
                user_scheduled_recordings.pop(rid, None)

        time.sleep(30)

@app.route("/api/recordings/start", methods=["POST"])
def api_start_recording():
    data = request.json
    channel_id_or_num = data.get("channel_id") or data.get("number")
    title = data.get("title", "")
    description = data.get("description", "")
    start = data.get("start")
    stop = data.get("stop")

    channel = get_channel_by_id_or_number(channel_id_or_num)
    if not channel:
        return jsonify({"error": "Invalid channel_id or number"}), 400

    stream_url = channel.get("stream")
    if not stream_url:
        return jsonify({"error": "Stream URL not found for channel"}), 400

    recording_id = f"{channel['id']}_{int(datetime.datetime.now().timestamp())}"

    metadata = {
        "channel": channel["id"],
        "title": title,
        "description": description,
        "start": start or datetime.datetime.now().isoformat(),
        "stop": stop,
    }

    filepath = start_recording(recording_id, stream_url, metadata)
    return jsonify({"recording_id": recording_id, "filepath": filepath})

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

@app.route("/api/recordings/schedule", methods=["POST"])
def api_schedule_recording():
    data = request.json
    channel_id_or_num = data.get("channel_id") or data.get("number")
    start_str = data.get("start")
    stop_str = data.get("stop")
    title = data.get("title", "")
    description = data.get("description", "")

    if not channel_id_or_num:
        return jsonify({"error": "Missing channel_id or number"}), 400
    if not start_str or not stop_str:
        return jsonify({"error": "Missing start or stop time"}), 400

    channel = get_channel_by_id_or_number(channel_id_or_num)
    if not channel:
        return jsonify({"error": "Invalid channel_id or number"}), 400

    try:
        start = datetime.datetime.fromisoformat(start_str)
        if start.tzinfo is None:
            start = UK_TZ.localize(start)
        stop = datetime.datetime.fromisoformat(stop_str)
        if stop.tzinfo is None:
            stop = UK_TZ.localize(stop)
    except Exception:
        return jsonify({"error": "Invalid start or stop time format, must be ISO"}), 400

    if stop <= start:
        return jsonify({"error": "Stop time must be after start time"}), 400

    recording_id = f"{channel['id']}_{int(start.timestamp())}"

    metadata = {
        "channel": channel["id"],
        "title": title,
        "description": description,
        "start": start.isoformat(),
        "stop": stop.isoformat(),
        "stream_url": channel.get("stream")
    }

    with scheduler_lock:
        if recording_id in user_scheduled_recordings:
            return jsonify({"error": "Recording already scheduled"}), 400
        user_scheduled_recordings[recording_id] = {
            "start": start,
            "stop": stop,
            "metadata": metadata
        }

    print(f"User scheduled recording {recording_id} from {start} to {stop}")
    return jsonify({"recording_id": recording_id, "metadata": metadata})

@app.route("/api/recordings/scheduled", methods=["GET"])
def api_list_scheduled_recordings():
    with scheduler_lock:
        recs = []
        for rid, info in user_scheduled_recordings.items():
            recs.append({
                "recording_id": rid,
                "start": info["start"].isoformat(),
                "stop": info["stop"].isoformat(),
                "metadata": info["metadata"]
            })
    return jsonify(recs)

if __name__ == "__main__":
    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    app.run(host="0.0.0.0", port=8080)
