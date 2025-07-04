# DVR Server API Documentation

This project is a **DVR Recording Server** that allows scheduling, managing, and listing TV recordings programmatically via a RESTful API. It uses `ffmpeg` to capture live streams and save recordings locally.



## Table of Contents

* [Overview](#overview)
* [Prerequisites](#prerequisites)
* [Setup](#setup)
* [API Endpoints](#api-endpoints)

  * [Start Recording](#start-recording)
  * [Cancel Recording](#cancel-recording)
  * [List Active Recordings](#list-active-recordings)
  * [List All Recordings](#list-all-recordings)
  * [Get MyShows List](#get-myshows-list)
  * [Health Check](#health-check)
* [Data Files](#data-files)
* [Recording Workflow](#recording-workflow)
* [Notes](#notes)
* [License](#license)



## Overview

The DVR Server provides an HTTP API to schedule live stream recordings by channel and program time, cancel ongoing recordings, and list current and past recordings. It relies on:

* A **channels JSON file** describing channel metadata and streams.
* An **EPG API** (Electronic Program Guide) providing program schedules per channel.
* `ffmpeg` to record streams.
* Thread-safe handling of active recordings.



## Prerequisites

* Python 3.7+
* `ffmpeg` installed and available in your system PATH
* Python dependencies (install via `pip install flask requests python-dateutil`)
* Running EPG server at `http://localhost:7070/api/epg` providing program guide JSON



## Setup

1. Clone or download this repository.

2. Place your `channels.json` file with channel info in the project root.

3. Ensure your EPG server is running and accessible.

4. Run the server:

   ```bash
   python dvr_server.py
   ```

5. The API listens on port `8080` by default.



## API Endpoints

### Start Recording

**POST** `/api/recordings/start`

Schedule a recording for a channel and optionally at a specific start time.

* **Request Body Example:**

  ```json
  {
    "channel": "channel_id_or_number",
    "start_time": "2025-07-04T21:00:00+02:00"
  }
  ```

  * `channel` (string): Required. Channel ID or channel number.
  * `start_time` (string, optional): ISO8601 formatted start time. If omitted, current live program is recorded.

* **Curl example:**

  ```bash
  curl -X POST http://localhost:8080/api/recordings/start \
    -H "Content-Type: application/json" \
    -d '{"channel": "101", "start_time": "2025-07-04T21:00:00+02:00"}'
  ```

* **Response Example:**

  ```json
  {
    "message": "Recording scheduled",
    "recording_id": "101_20250704T210000",
    "channel": "News Channel",
    "program_title": "Evening News",
    "start_time": "2025-07-04T21:00:00+02:00",
    "stop_time": "2025-07-04T21:30:00+02:00",
    "file_path": "recordings/20250704T210000_101_Evening_News.mp4"
  }
  ```

* **Errors:**

  * 400 Bad Request if missing parameters or invalid time format.
  * 404 Not Found if channel not found.
  * 400 Bad Request if no EPG data available.



### Cancel Recording

**POST** `/api/recordings/cancel`

Cancel an ongoing recording.

* **Request Body Example:**

  ```json
  {
    "recording_id": "101_20250704T210000"
  }
  ```

* **Curl example:**

  ```bash
  curl -X POST http://localhost:8080/api/recordings/cancel \
    -H "Content-Type: application/json" \
    -d '{"recording_id": "101_20250704T210000"}'
  ```

* **Response Example:**

  ```json
  {
    "message": "Recording 101_20250704T210000 canceled"
  }
  ```

* **Errors:**

  * 400 Bad Request if missing `recording_id`.
  * 404 Not Found if recording not found.



### List Active Recordings

**GET** `/api/recordings`

Returns a list of recordings currently in progress or scheduled.

* **Curl example:**

  ```bash
  curl http://localhost:8080/api/recordings
  ```

* **Response Example:**

  ```json
  [
    {
      "recording_id": "101_20250704T210000",
      "channel_id": "101",
      "program_title": "Evening News",
      "start_time": "2025-07-04T21:00:00+02:00",
      "stop_time": "2025-07-04T21:30:00+02:00",
      "file_path": "recordings/20250704T210000_101_Evening_News.mp4",
      "canceled": false
    }
  ]
  ```



### List All Recordings

**GET** `/api/recordings/all`

Returns all saved recording files from the `recordings/` directory, including past recordings.

* **Curl example:**

  ```bash
  curl http://localhost:8080/api/recordings/all
  ```

* **Response Example:**

  ```json
  [
    {
      "file_name": "20250704T210000_101_Evening_News.mp4",
      "channel_id": "101",
      "program_title": "Evening News",
      "start_time": "2025-07-04T21:00:00",
      "file_path": "recordings/20250704T210000_101_Evening_News.mp4"
    }
  ]
  ```



### Get MyShows List

**GET** `/api/myshows`

Returns the list of saved shows (recordings) tracked in `myshows.json`.

* **Curl example:**

  ```bash
  curl http://localhost:8080/api/myshows
  ```

* **Response Example:**

  ```json
  [
    {
      "recording_id": "101_20250704T210000",
      "channel_id": "101",
      "program_title": "Evening News",
      "start_time": "2025-07-04T21:00:00+02:00",
      "stop_time": "2025-07-04T21:30:00+02:00",
      "file_path": "recordings/20250704T210000_101_Evening_News.mp4"
    }
  ]
  ```



### Health Check

**GET** `/`

Basic server status check.

* **Curl example:**

  ```bash
  curl http://localhost:8080/
  ```

* **Response Example:**

  ```json
  {
    "message": "DVR Recording Server is running."
  }
  ```



## Data Files

* `channels.json`: List of channels with `id`, `number`, `name`, and `stream` URL.
* `myshows.json`: JSON array tracking saved recordings metadata.
* `recordings/`: Directory where `.mp4` recordings are saved.



## Recording Workflow

1. **Schedule:** User requests to start recording a channel and optionally specify a start time.
2. **EPG Lookup:** Server fetches program info from EPG API to find the program details.
3. **Recording:** A new thread starts, waiting until the start time, then runs `ffmpeg` to record the stream.
4. **Cancel:** User can cancel an active recording, sending `SIGINT` to the `ffmpeg` process.
5. **Completion:** Upon completion, recording info is saved to `myshows.json`.
6. **Listing:** Users can query active recordings or all saved recordings.



## Notes

* The server uses threading to allow multiple simultaneous recordings.
* Filenames are sanitized and formatted as `<timestamp>_<channel_id>_<program_title>.mp4`.
* The server expects the EPG API to be available at `http://localhost:7070/api/epg`.
* The recordings directory is created automatically if missing.
* Timezones are handled using ISO8601 and local timezone fallback.



## License

This project is provided as-is under the MIT License.
