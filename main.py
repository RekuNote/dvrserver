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

app = Flask(__name__)

RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Active recording processes: {recording_id: {"process": Popen, "filepath": str, "metadata": dict}}
active_recordings = {}

# Load channels.json to get stream URLs
with open("channels.json", "r") as f:
    channels = {c["id"]: c for c in json.load(f)}

# Build reverse lookup: channel number -> channel_id
number_to_channel_id = {c["number"]: c["id"] for c in channels.values()}

UK_TZ = pytz.timezone("Europe/London")
EPG_URL = "https://raw.githubusercontent.com/dp247/Freeview-EPG/master/epg.xml"

def safe_filename(s):
    import re
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
        # Sort programs by start time
        for chan in epg:
            epg[chan].sort(key=lambda x: x["start"])
        return epg
    except Exception as e:
        print("Error fetching EPG:", e)
        return {}

scheduler_lock = threading.Lock()
scheduled_recordings = {}  # recording_id: {"start": datetime, "stop": datetime, "metadata": dict}

def scheduler_loop():
    while True:
        epg = fetch_epg()
        now = datetime.datetime.now(UK_TZ)

        with scheduler_lock:
            # Check for programs starting soon (within next 1 min)
            for chan_id, programs in epg.items():
                for prog in programs:
                    rid = f"{chan_id}_{int(prog['start'].timestamp())}"
                    if rid in scheduled_recordings or rid in active_recordings:
                        continue  # already scheduled or recording

                    # Schedule program if start time is within the next 60 seconds
                    if 0 <= (prog["start"] - now).total_seconds() < 60:
                        # Start recording
                        stream_url = channels[chan_id]["stream"]
                        metadata = {
                            "channel": chan_id,
                            "title": prog["title"],
                            "description": prog["desc"],
                            "start": prog["start"].isoformat(),
                            "stop": prog["stop"].isoformat()
                        }
                        start_recording(rid, stream_url, metadata)
                        scheduled_recordings[rid] = {
                            "start": prog["start"],
                            "stop": prog["stop"],
                            "metadata": metadata
                        }
                        print(f"Scheduled and started recording {rid}")

            # Stop recordings that have passed stop time
            to_stop = []
            for rid, info in list(scheduled_recordings.items()):
                if now >= info["stop"]:
                    stop_recording(rid)
                    to_stop.append(rid)
            for rid in to_stop:
                scheduled_recordings.pop(rid, None)

        time.sleep(30)

@app.route("/api/recordings/start", methods=["POST"])
def api_start_recording():
    data = request.json

    channel_id = data.get("channel_id")
    number = data.get("number")   # new param for channel number
    title = data.get("title", "")
    description = data.get("description", "")
    start_time_str = data.get("start_time")  # HH:MM:SS

    # Resolve channel_id by number if number is given
    if number:
        channel_id = number_to_channel_id.get(number)
        if not channel_id:
            return jsonify({"error": "Invalid channel number"}), 400

    if not channel_id or channel_id not in channels:
        return jsonify({"error": "Invalid channel_id"}), 400

    stream_url = channels[channel_id]["stream"]
    if not stream_url:
        return jsonify({"error": "Stream URL not found for channel"}), 400

    # Parse start time from HH:MM:SS (optional)
    if start_time_str:
        try:
            h, m, s = map(int, start_time_str.split(":"))
            now = datetime.datetime.now(UK_TZ)
            start_dt = now.replace(hour=h, minute=m, second=s, microsecond=0)
            # If time already passed today, assume next day
            if start_dt < now:
                start_dt += datetime.timedelta(days=1)
            start_iso = start_dt.isoformat()
        except Exception:
            return jsonify({"error": "Invalid start_time format, use HH:MM:SS"}), 400
    else:
        start_iso = datetime.datetime.now(UK_TZ).isoformat()

    recording_id = f"{channel_id}_{int(datetime.datetime.now().timestamp())}"

    metadata = {
        "channel": channel_id,
        "title": title,
        "description": description,
        "start": start_iso,
        "stop": data.get("stop")
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

@app.route("/api/recordings/saved", methods=["GET"])
def api_list_saved_recordings():
    recordings_list = []
    for filename in os.listdir(RECORDINGS_DIR):
        if filename.endswith(".mp4"):
            filepath = os.path.join(RECORDINGS_DIR, filename)
            meta_filepath = filepath + ".json"
            metadata = {}
            if os.path.exists(meta_filepath):
                try:
                    with open(meta_filepath, "r") as mf:
                        metadata = json.load(mf)
                except Exception as e:
                    print(f"Failed to load metadata for {filename}: {e}")
            recordings_list.append({
                "filename": filename,
                "filepath": filepath,
                "metadata": metadata
            })
    return jsonify(recordings_list)

if __name__ == "__main__":
    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    app.run(host="0.0.0.0", port=8080)
