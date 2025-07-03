# DVRServer
Documentation

## 1. `POST /api/recordings/start` – Start or schedule a recording

This endpoint is smart:

- If `start` is in the **future**, it **schedules** the recording.
- If `start` is **now or omitted**, it **starts immediately**.

### A. Start a recording **immediately**

```bash
curl -X POST http://localhost:8080/api/recordings/start \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "bbc1",
    "title": "News at Ten",
    "description": "Evening news on BBC One"
  }'
````

### B. Schedule a recording **in the future**

```bash
curl -X POST http://localhost:8080/api/recordings/start \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "bbc2",
    "title": "Panorama",
    "description": "Documentary",
    "start": "2025-07-03T21:00:00+01:00",
    "stop": "2025-07-03T22:00:00+01:00"
  }'
```

> `start` and `stop` must be in **ISO 8601 format**, ideally with timezone info (`+01:00` for UK summer time).

---

## 2. `POST /api/recordings/stop` – Manually stop a running recording

You’ll need the `recording_id` returned from a `start` request.

```bash
curl -X POST http://localhost:8080/api/recordings/stop \
  -H "Content-Type: application/json" \
  -d '{
    "recording_id": "bbc1_1720001234"
  }'
```

---

## 3. `GET /api/recordings` – List all **currently active** recordings

```bash
curl http://localhost:8080/api/recordings
```

**Response:**

```json
[
  {
    "recording_id": "bbc1_1720001234",
    "filepath": "recordings/2025-07-03T20:59:59+01:00_BBC_One_News_at_Ten.mp4",
    "metadata": {
      "channel": "bbc1",
      "title": "News at Ten",
      "description": "Evening news",
      "start": "2025-07-03T20:59:59+01:00",
      "stop": null
    }
  }
]
```

---

## 4. `GET /api/recordings/scheduled` – List all **future scheduled** recordings

```bash
curl http://localhost:8080/api/recordings/scheduled
```

**Response:**

```json
[
  {
    "recording_id": "bbc2_1720004321",
    "start": "2025-07-03T21:00:00+01:00",
    "stop": "2025-07-03T22:00:00+01:00",
    "metadata": {
      "channel": "bbc2",
      "title": "Panorama",
      "description": "Documentary",
      "start": "2025-07-03T21:00:00+01:00",
      "stop": "2025-07-03T22:00:00+01:00"
    }
  }
]
```

---

## `channels.json`

Copy the `channels.json` file from your `tvserver/` directory to your project directory. Ensure the following formatting:

```json
[
  {
    "id": "bbc1",
    "name": "BBC One",
    "stream": "http://your-stream-url/bbc1.m3u8"
  },
  {
    "id": "bbc2",
    "name": "BBC Two",
    "stream": "http://your-stream-url/bbc2.m3u8"
  }
]
```

> Replace `"stream"` URLs with valid `.m3u8` or direct media streams.

---

## Testing Tips

* Start the server with:

  ```bash
  python main.py
  ```
* Use a tool like **Postman**, **Insomnia**, or just `curl` for testing.
* Keep your stream URLs short and working to avoid `ffmpeg` hanging.
