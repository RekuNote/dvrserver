
# DVRServer API Documentation

---

## 1. Start a Recording

**Endpoint:**
`POST /api/recordings/start`

**Description:**
Starts a recording on a specified channel. You can specify the channel either by its `channel_id` or its `number` (channel number). You may optionally specify the start time (`start_time`), title, description and stop time.

---

### Request JSON Parameters

| Parameter     | Type   | Required                    | Description                                                                                                         |
| ------------- | ------ | --------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `channel_id`  | string | Either this or `number`     | The unique ID of the channel (e.g., `"BBCOneLondonHD.uk"`).                                                         |
| `number`      | string | Either this or `channel_id` | The channel number as a string (e.g., `"101"`). If provided, it will be mapped to the corresponding `channel_id`.   |
| `title`       | string | No                          | Title of the recording. If omitted, defaults to `"unknown"`.                                                        |
| `description` | string | No                          | Description of the recording.                                                                                       |
| `start_time`  | string | No                          | Start time in 24-hour format `"HH:MM:SS"` (e.g., `"21:30:00"`). Defaults to current time in Europe/London timezone. |
| `stop`        | string | No                          | Stop time in ISO 8601 format (e.g., `"2025-07-03T22:30:00+01:00"`).                                                 |

---

### Behavior Notes:

* If both `channel_id` and `number` are provided, `number` will be prioritised to look up the channel.
* If `start_time` is given, it is interpreted as a time *today* in Europe/London timezone. If that time has already passed today, it will schedule for the same time *tomorrow*.
* The `stop` parameter can be used to specify when to stop recording. If omitted, recording will continue until manually stopped or the process is terminated.

---

### Successful Response

```json
{
  "recording_id": "BBCOneLondonHD.uk_1720405800",
  "filepath": "recordings/2025-07-03T21:30:00+01:00_BBCOneLondonHD_The_Evening_Show.mp4"
}
```

---

### Error Responses

* Invalid channel number:

```json
{
  "error": "Invalid channel number"
}
```

* Invalid channel ID:

```json
{
  "error": "Invalid channel_id"
}
```

* Invalid `start_time` format:

```json
{
  "error": "Invalid start_time format, use HH:MM:SS"
}
```

---

### Examples

1. **Start recording by channel ID immediately**

```bash
curl -X POST http://localhost:8080/api/recordings/start \
-H "Content-Type: application/json" \
-d '{
  "channel_id": "BBCOneLondonHD.uk",
  "title": "Evening News",
  "description": "BBC One Evening News"
}'
```

2. **Start recording by channel number immediately**

```bash
curl -X POST http://localhost:8080/api/recordings/start \
-H "Content-Type: application/json" \
-d '{
  "number": "101",
  "title": "Evening News",
  "description": "BBC One Evening News"
}'
```

3. **Start recording by channel number at specific time 21:00:00 today or tomorrow**

```bash
curl -X POST http://localhost:8080/api/recordings/start \
-H "Content-Type: application/json" \
-d '{
  "number": "101",
  "start_time": "21:00:00",
  "title": "Prime Time Show",
  "description": "Prime time special"
}'
```

4. **Start recording with stop time specified**

```bash
curl -X POST http://localhost:8080/api/recordings/start \
-H "Content-Type: application/json" \
-d '{
  "channel_id": "BBCOneLondonHD.uk",
  "title": "Late Show",
  "start_time": "23:30:00",
  "stop": "2025-07-03T00:30:00+01:00",
  "description": "Late night show"
}'
```

---

## 2. Stop a Recording

**Endpoint:**
`POST /api/recordings/stop`

**Description:**
Stops an active recording using the `recording_id`.

---

### Request JSON Parameters

| Parameter      | Type   | Required | Description                                                                      |
| -------------- | ------ | -------- | -------------------------------------------------------------------------------- |
| `recording_id` | string | Yes      | The ID of the recording to stop (from start response or active recordings list). |

---

### Successful Response

```json
{
  "status": "stopped",
  "recording_id": "BBCOneLondonHD.uk_1720405800"
}
```

---

### Error Responses

* Missing recording ID:

```json
{
  "error": "Missing recording_id"
}
```

* Recording not found:

```json
{
  "error": "Recording not found"
}
```

---

### Example

```bash
curl -X POST http://localhost:8080/api/recordings/stop \
-H "Content-Type: application/json" \
-d '{
  "recording_id": "BBCOneLondonHD.uk_1720405800"
}'
```

---

## 3. List Active Recordings

**Endpoint:**
`GET /api/recordings`

**Description:**
Returns a JSON array of all currently active (running) recordings with metadata.

---

### Successful Response Example

```json
[
  {
    "recording_id": "BBCOneLondonHD.uk_1720405800",
    "filepath": "recordings/2025-07-03T21:30:00+01:00_BBCOneLondonHD_The_Evening_Show.mp4",
    "metadata": {
      "channel": "BBCOneLondonHD.uk",
      "title": "The Evening Show",
      "description": "BBC One Evening News",
      "start": "2025-07-03T21:30:00+01:00",
      "stop": null
    }
  }
]
```

---

### Example

```bash
curl http://localhost:8080/api/recordings
```

---

## 4. List All Saved Recordings on Disk

**Endpoint:**
`GET /api/recordings/saved`

**Description:**
Returns a JSON array of all recordings saved on disk in the `recordings` directory. Each includes filename, full filepath and metadata loaded from the accompanying `.json` file (if available).

---

### Successful Response Example

```json
[
  {
    "filename": "2025-07-03T21:30:00+01:00_BBCOneLondonHD_The_Evening_Show.mp4",
    "filepath": "recordings/2025-07-03T21:30:00+01:00_BBCOneLondonHD_The_Evening_Show.mp4",
    "metadata": {
      "channel": "BBCOneLondonHD.uk",
      "title": "The Evening Show",
      "description": "BBC One Evening News",
      "start": "2025-07-03T21:30:00+01:00",
      "stop": null
    }
  },
  {
    "filename": "2025-07-02T20:00:00+01:00_BBCTwoHD_Another_Show.mp4",
    "filepath": "recordings/2025-07-02T20:00:00+01:00_BBCTwoHD_Another_Show.mp4",
    "metadata": {
      "channel": "BBCTwoHD.uk",
      "title": "Another Show",
      "description": "BBC Two Drama",
      "start": "2025-07-02T20:00:00+01:00",
      "stop": "2025-07-02T21:00:00+01:00"
    }
  }
]
```

---

### Example

```bash
curl http://localhost:8080/api/recordings/saved
```

---

# Summary

* `/api/recordings/start`
  Start a new recording by either `channel_id` or `number`, optionally specifying `start_time` (HH\:MM\:SS), `stop`, `title` and `description`.

* `/api/recordings/stop`
  Stop an active recording by `recording_id`.

* `/api/recordings`
  List all currently active recordings.

* `/api/recordings/saved`
  List all saved recordings on disk with metadata.
