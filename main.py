import os
import json
import threading
import subprocess
import datetime
import time
import signal
from flask import Flask, request, jsonify, abort
import requests
from dateutil import parser
from dateutil.tz import tzlocal
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
PORT = 8080

# Paths
CHANNELS_FILE = 'channels.json'   # Your channel list JSON (from snippet)
RECORDINGS_DIR = 'recordings'     # Directory to store recordings
MYSHOWS_FILE = 'myshows.json'
myshows_lock = threading.Lock()

# Load channels once on startup
with open(CHANNELS_FILE, 'r') as f:
    CHANNELS = json.load(f)

# Maps for quick lookup by id or number
CHANNELS_BY_ID = {ch['id']: ch for ch in CHANNELS}
CHANNELS_BY_NUMBER = {ch['number']: ch for ch in CHANNELS}

# Active recordings info storage (thread-safe)
active_recordings_lock = threading.Lock()
active_recordings = {}  # key: recording_id, value: Recording object

# Define myshows stuff
def load_myshows():
    if os.path.exists(MYSHOWS_FILE):
        with open(MYSHOWS_FILE, 'r') as f:
            return json.load(f)
    return []

# Define a Recording class to track recording processes and details
class Recording:
    def __init__(self, channel_id, program_title, start_time, stop_time, stream_url):
        self.channel_id = channel_id
        self.program_title = program_title
        self.start_time = start_time  # datetime object
        self.stop_time = stop_time    # datetime object
        self.stream_url = stream_url
        self.process = None  # ffmpeg subprocess
        self.id = f"{channel_id}_{start_time.strftime('%Y%m%dT%H%M%S')}"
        self.file_path = self._make_filename()
        self.thread = None
        self.canceled = False

    def cancel(self):
        self.canceled = True
        if self.process and self.process.poll() is None:
            # Send SIGINT (Ctrl+C) to the ffmpeg process for graceful shutdown
            try:
                print(f"Sending SIGINT to recording {self.id}")
                self.process.send_signal(signal.SIGINT)
            except Exception as e:
                print(f"Error sending SIGINT to ffmpeg: {e}")
        # Remove from active recordings dict safely
        with active_recordings_lock:
            active_recordings.pop(self.id, None)

    def _sanitize(self, s):
        # Simple sanitize for filename - replace spaces and slashes
        return "".join(c if c.isalnum() or c in " _-()" else "_" for c in s)

    def _make_filename(self):
        timestamp = self.start_time.strftime('%Y%m%dT%H%M%S')
        safe_title = self._sanitize(self.program_title)
        filename = f"{timestamp}_{self.channel_id}_{safe_title}.mp4"
        return os.path.join(RECORDINGS_DIR, filename)

    def start_recording(self):
        if self.canceled:
            print(f"Recording {self.id} canceled before start")
            return

        # Ensure recordings dir exists
        if not os.path.exists(RECORDINGS_DIR):
            os.makedirs(RECORDINGS_DIR)

        now = datetime.datetime.now(tzlocal())
        start = max(self.start_time, now)
        duration_seconds = int((self.stop_time - start).total_seconds())
        if duration_seconds <= 0:
            print(f"Invalid recording duration for {self.id}, skipping")
            return

        cmd = [
            "ffmpeg",
            "-y",
            "-re",
            "-i", self.stream_url,
            "-c", "copy",
            "-t", str(duration_seconds),
            self.file_path
        ]
        try:
            print(f"Running ffmpeg command: {' '.join(cmd)}")
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Wait for process to finish
            stdout, stderr = self.process.communicate()

            if self.process.returncode != 0:
                print(f"ffmpeg error for recording {self.id}: {stderr.decode(errors='ignore')}")
            else:
                print(f"ffmpeg finished recording {self.id} successfully")
                # Save recording info to myshows.json on success
                record = {
                    "recording_id": self.id,
                    "channel_id": self.channel_id,
                    "program_title": self.program_title,
                    "start_time": self.start_time.isoformat(),
                    "stop_time": self.stop_time.isoformat(),
                    "file_path": self.file_path,
                }
                save_to_myshows(record)

        except Exception as e:
            print(f"Error running ffmpeg: {e}")
        finally:
            # Clean up from active recordings
            with active_recordings_lock:
                active_recordings.pop(self.id, None)

def fetch_epg():
    try:
        r = requests.get("http://localhost:7070/api/epg", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error fetching EPG: {e}")
        return None


def find_channel(identifier):
    # identifier can be ID or number (string)
    if identifier in CHANNELS_BY_ID:
        return CHANNELS_BY_ID[identifier]
    if identifier in CHANNELS_BY_NUMBER:
        return CHANNELS_BY_NUMBER[identifier]
    return None


def schedule_recording(channel_id, start_time=None):
    epg_data = fetch_epg()
    if not epg_data or channel_id not in epg_data:
        return None, "EPG data missing or channel not found"

    channel_epg = epg_data[channel_id]

    # Pick the current program info from epg
    now = datetime.datetime.now(tzlocal())

    # Find the program which matches the start_time if specified, else current
    program = None
    for prog in channel_epg.get('programs', []):
        prog_start = parser.isoparse(prog['start'])
        prog_stop = parser.isoparse(prog['stop'])

        if start_time:
            # If start_time in the future and matches program timing
            # We pick the program whose start time is closest after start_time
            if prog_start <= start_time < prog_stop:
                program = prog
                break
            elif start_time < prog_start:
                # If user start_time is before a program start, pick this program as next upcoming
                program = prog
                break
        else:
            # No start time specified - pick the currently playing program
            if prog_start <= now < prog_stop:
                program = prog
                break

    if not program:
        # Fallback: pick the first program if nothing matched
        if channel_epg.get('programs'):
            program = channel_epg['programs'][0]
        else:
            return None, "No program info available for this channel"

    # Use start_time from program if none provided
    prog_start = parser.isoparse(program['start'])
    prog_stop = parser.isoparse(program['stop'])

    # If user start_time is earlier than program start, use program start
    effective_start = start_time or prog_start
    now = datetime.datetime.now(tzlocal())

    if effective_start < now:
        # If requested start already passed, start immediately
        effective_start = now

    # The stream URL can be overridden by program stream, else channel stream
    stream_url = channel_epg.get('stream') or CHANNELS_BY_ID[channel_id]['stream']

    recording = Recording(
        channel_id=channel_id,
        program_title=program['title'],
        start_time=effective_start,
        stop_time=prog_stop,
        stream_url=stream_url,
    )

    def recording_thread_func():
        delay = (recording.start_time - datetime.datetime.now(tzlocal())).total_seconds()
        if delay > 0:
            time.sleep(delay)
        if recording.canceled:
            return
        print(f"Starting recording {recording.id}")
        recording.start_recording()
        print(f"Finished recording {recording.id}")

    # Start a thread to handle the recording timing
    t = threading.Thread(target=recording_thread_func, daemon=True)
    recording.thread = t

    with active_recordings_lock:
        active_recordings[recording.id] = recording
    t.start()

    return recording, None


@app.route('/api/recordings/start', methods=['POST'])
def api_start_recording():
    data = request.json
    if not data or ('channel' not in data):
        return jsonify({"error": "Missing channel ID or number"}), 400

    channel_identifier = str(data['channel'])
    start_time_str = data.get('start_time')

    channel = find_channel(channel_identifier)
    if not channel:
        return jsonify({"error": f"Channel '{channel_identifier}' not found"}), 404

    start_time = None
    if start_time_str:
        try:
            start_time = parser.isoparse(start_time_str)
            if start_time.tzinfo is None:
                # Assume local timezone if no tzinfo
                start_time = start_time.replace(tzinfo=tzlocal())
        except Exception:
            return jsonify({"error": "Invalid start_time format, must be ISO8601"}), 400

    recording, err = schedule_recording(channel['id'], start_time)
    if err:
        return jsonify({"error": err}), 400

    return jsonify({
        "message": "Recording scheduled",
        "recording_id": recording.id,
        "channel": channel['name'],
        "program_title": recording.program_title,
        "start_time": recording.start_time.isoformat(),
        "stop_time": recording.stop_time.isoformat(),
        "file_path": recording.file_path
    })


@app.route('/api/recordings/cancel', methods=['POST'])
def api_cancel_recording():
    data = request.json
    if not data or 'recording_id' not in data:
        return jsonify({"error": "Missing recording_id"}), 400

    recording_id = data['recording_id']
    with active_recordings_lock:
        recording = active_recordings.get(recording_id)

    if not recording:
        return jsonify({"error": "Recording not found"}), 404

    recording.cancel()
    return jsonify({"message": f"Recording {recording_id} canceled"})


@app.route('/api/recordings', methods=['GET'])
def api_list_active_recordings():
    with active_recordings_lock:
        recordings_list = []
        for rec in active_recordings.values():
            recordings_list.append({
                "recording_id": rec.id,
                "channel_id": rec.channel_id,
                "program_title": rec.program_title,
                "start_time": rec.start_time.isoformat(),
                "stop_time": rec.stop_time.isoformat(),
                "file_path": rec.file_path,
                "canceled": rec.canceled,
            })
    return jsonify(recordings_list)


@app.route('/api/recordings/all', methods=['GET'])
def api_list_all_recordings():
    if not os.path.exists(RECORDINGS_DIR):
        os.makedirs(RECORDINGS_DIR)

    with myshows_lock:
        myshows = load_myshows()
        existing_ids = {r.get("recording_id") for r in myshows}

        updated = False
        files = []

        for fname in os.listdir(RECORDINGS_DIR):
            if fname.endswith('.mp4'):
                try:
                    # filename format: YYYYMMDDTHHMMSS_channelid_programtitle.mp4
                    parts = fname[:-4].split('_', 2)
                    if len(parts) < 3:
                        continue

                    timestamp_str, channel_id, program_title = parts
                    start_time = datetime.datetime.strptime(timestamp_str, '%Y%m%dT%H%M%S')

                    # Now construct recording_id same way as in Recording class:
                    record_id = f"{channel_id}_{timestamp_str}"

                    files.append({
                        "file_name": fname,
                        "channel_id": channel_id,
                        "program_title": program_title,
                        "start_time": start_time.isoformat(),
                        "file_path": os.path.join(RECORDINGS_DIR, fname)
                    })

                    # Add to myshows if missing
                    if record_id not in existing_ids:
                        new_record = {
                            "recording_id": record_id,
                            "channel_id": channel_id,
                            "program_title": program_title,
                            "start_time": start_time.isoformat(),
                            "stop_time": None,  # You can improve this later
                            "file_path": os.path.join(RECORDINGS_DIR, fname)
                        }
                        myshows.append(new_record)
                        existing_ids.add(record_id)
                        updated = True

                except Exception as e:
                    print(f"Error parsing filename {fname}: {e}")
                    continue

        if updated:
            with open(MYSHOWS_FILE, 'w') as f:
                json.dump(myshows, f, indent=2)

    return jsonify(files)

@app.route('/')
def index():
    return jsonify({"message": "DVR Recording Server is running."})

@app.route('/api/myshows', methods=['GET'])
def api_myshows():
    with myshows_lock:
        shows = load_myshows()
    return jsonify(shows)

if __name__ == '__main__':
    if not os.path.exists(RECORDINGS_DIR):
        os.makedirs(RECORDINGS_DIR)
    app.run(host='0.0.0.0', port=PORT, debug=True)
