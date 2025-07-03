# DVR Server API Documentation

## Overview

This API allows you to manage live and scheduled TV recordings using channel info and EPG schedules.

You can:

* **Start/stop immediate recordings**
* **Schedule recordings for the future**
* **List active recordings**
* **List scheduled recordings**

# Base URL

```
http://<server-host>:8080/
```

Replace `<server-host>` with your server IP or hostname.

# Endpoints

## 1. Start a recording immediately

```
POST /api/recordings/start
```

Start recording a given channel immediately.

### Request JSON body

| Field         | Type   | Required | Description                                                                    |
| ------------- | ------ | -------- | ------------------------------------------------------------------------------ |
| `channel_id`  | string | Cond.    | The channel ID (e.g. `"BBCOneLondonHD.uk"`). Required if `number` missing.     |
| `number`      | string | Cond.    | Channel number as string (e.g. `"101"`). Required if `channel_id` missing.     |
| `title`       | string | No       | Title for the recording metadata (e.g. `"News at 6"`).                         |
| `description` | string | No       | Description for the recording metadata.                                        |
| `start`       | string | No       | ISO 8601 datetime string of recording start time (ignored, uses current time). |
| `stop`        | string | No       | ISO 8601 datetime string of stop time (ignored for immediate recording).       |

### Notes

* `channel_id` or `number` **must** be provided.
* The recording starts immediately on the channel’s stream URL.
* Returns a unique `recording_id` to identify this recording.

### Response JSON

```json
{
  "recording_id": "BBCOneLondonHD.uk_1695000000",
  "filepath": "recordings/2025-07-03T13:15:00+01:00_BBCOneLondonHD.uk_News at 6.mp4"
}
```

### Example

```bash
curl -X POST http://localhost:8080/api/recordings/start \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "BBCOneLondonHD.uk", "title": "News at 6"}'
```

## 2. Stop a recording

```
POST /api/recordings/stop
```

Stop a currently running recording by its `recording_id`.

### Request JSON body

| Field          | Type   | Required | Description                  |
| -------------- | ------ | -------- | ---------------------------- |
| `recording_id` | string | Yes      | ID of the recording to stop. |

### Response JSON

Success:

```json
{
  "status": "stopped",
  "recording_id": "BBCOneLondonHD.uk_1695000000"
}
```

Failure (recording not found):

```json
{
  "error": "Recording not found"
}
```

### Example

```bash
curl -X POST http://localhost:8080/api/recordings/stop \
  -H "Content-Type: application/json" \
  -d '{"recording_id": "BBCOneLondonHD.uk_1695000000"}'
```


## 3. List currently active recordings

```
GET /api/recordings
```

Returns all recordings currently running.

### Response JSON

Array of active recordings:

```json
[
  {
    "recording_id": "BBCOneLondonHD.uk_1695000000",
    "filepath": "recordings/2025-07-03T13:15:00+01:00_BBCOneLondonHD.uk_News at 6.mp4",
    "metadata": {
      "channel": "BBCOneLondonHD.uk",
      "title": "News at 6",
      "description": "Evening news",
      "start": "2025-07-03T13:15:00+01:00",
      "stop": null
    }
  }
]
```

### Example

```bash
curl http://localhost:8080/api/recordings
```

## 4. Schedule a recording for the future

```
POST /api/recordings/schedule
```

Schedule a recording to start and stop at specified future times.

### Request JSON body

| Field         | Type   | Required | Description                                                            |
| ------------- | ------ | -------- | ---------------------------------------------------------------------- |
| `channel_id`  | string | Cond.    | Channel ID (e.g. `"BBCOneLondonHD.uk"`). Required if `number` missing. |
| `number`      | string | Cond.    | Channel number (e.g. `"101"`). Required if `channel_id` missing.       |
| `start`       | string | Yes      | ISO 8601 datetime with timezone. When to start recording.              |
| `stop`        | string | Yes      | ISO 8601 datetime with timezone. When to stop recording.               |
| `title`       | string | No       | Title for the recording metadata.                                      |
| `description` | string | No       | Description for the recording metadata.                                |

### Notes

* The scheduler will start recording automatically when the start time approaches.
* Stop time must be after start time.
* Channel stream URL is resolved at scheduling time.
* Returns a unique `recording_id`.

### Response JSON

```json
{
  "recording_id": "BBCOneLondonHD.uk_1751544900",
  "metadata": {
    "channel": "BBCOneLondonHD.uk",
    "title": "Scheduled Show",
    "description": "My scheduled recording",
    "start": "2025-07-03T15:00:00+01:00",
    "stop": "2025-07-03T15:30:00+01:00",
    "stream_url": "https://..."
  }
}
```

### Example

```bash
curl -X POST http://localhost:8080/api/recordings/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "BBCOneLondonHD.uk",
    "start": "2025-07-03T15:00:00+01:00",
    "stop": "2025-07-03T15:30:00+01:00",
    "title": "Scheduled Show",
    "description": "My scheduled recording"
  }'
```

## 5. List all user scheduled (pending) recordings

```
GET /api/recordings/scheduled
```

Returns all future recordings the user has scheduled but not yet started or completed.

### Response JSON

Array of scheduled recordings:

```json
[
  {
    "recording_id": "BBCOneLondonHD.uk_1751544900",
    "start": "2025-07-03T15:00:00+01:00",
    "stop": "2025-07-03T15:30:00+01:00",
    "metadata": {
      "channel": "BBCOneLondonHD.uk",
      "title": "Scheduled Show",
      "description": "My scheduled recording",
      "start": "2025-07-03T15:00:00+01:00",
      "stop": "2025-07-03T15:30:00+01:00",
      "stream_url": "https://..."
    }
  }
]
```

### Example

```bash
curl http://localhost:8080/api/recordings/scheduled
```

# Additional Information

### Timezones

* All datetime strings must be ISO 8601 formatted, including timezone offset (e.g. `"2025-07-03T15:00:00+01:00"`).
* The server uses Europe/London timezone internally and will localize naive timestamps accordingly.

### Filenames

* Recorded files are saved to the `recordings/` directory with sanitized filenames including start time, channel ID, and title.

### Errors

* If required parameters are missing or invalid, the API will respond with status 400 and a JSON error message.
* If trying to schedule a recording already scheduled for the exact same start time, the API will return error 400.

### Concurrency and Threading

* The scheduler runs in a separate background thread, starting and stopping scheduled recordings automatically.
* Manual start/stop endpoints remain fully functional.

# Example Workflow

1. **Schedule a future recording**
   POST to `/api/recordings/schedule` with channel and start/stop times.

2. **List scheduled recordings**
   GET `/api/recordings/scheduled`

3. **Wait for the scheduler to start recording at the right time**
   The recording starts automatically in the background.

4. **List active recordings**
   GET `/api/recordings`

5. **Stop a recording manually (if desired)**
   POST to `/api/recordings/stop` with the recording ID.

If you want, I can also generate a **Postman collection** or a **Python client example** for easy API interaction. Just say the word!
