# Hand Gesture Controlled Media Player (FastAPI)

Control media using hand gestures from a local webcam or a phone camera URL stream.

## Features

- FastAPI backend with realtime WebSocket status
- Hand gesture recognition via OpenCV + MediaPipe
- Supports local webcam and remote camera URL stream (phone camera)
- Controls system media and audio
- Modern web dashboard for status and manual control

## Gesture Mapping

- `OPEN_PALM` -> Play/Pause
- `THUMB_UP` -> Volume Up
- `THUMB_DOWN` -> Volume Down
- `V_SIGN` -> Next Track
- `FIST` -> Previous Track
- `PINCH` -> Mute Toggle

## Requirements

- Windows 10/11 (recommended for this setup)
- Python 3.10+
- Phone camera app if local webcam is unavailable

## Setup

```bash
cd c:/PROJECTS/Hand-Gesture-Base-Music-Player-Controller
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

- http://127.0.0.1:8000

## API

- `POST /api/gesture/start`
  - local webcam: `camera_index=0`
  - phone stream: `camera_source=http://<phone-ip>:8080/video`
- `POST /api/gesture/stop`
- `POST /api/media/{action}` where action is one of:
  - `play-pause`
  - `next`
  - `previous`
  - `volume-up`
  - `volume-down`
  - `mute-toggle`
- `GET /api/status`
- `GET /ws/status`

## Phone Camera Setup (URL Stream)

Use this when your laptop webcam is broken or inaccessible.

1. Install a phone camera app:
   - Android: IP Webcam, DroidCam, Iriun
   - iPhone: EpocCam, iVCam-compatible apps
2. Connect phone and PC to the same network.
3. Start streaming in the phone app and copy the stream URL.
   - Common formats:
     - `http://192.168.x.x:8080/video` (MJPEG)
     - `rtsp://192.168.x.x:8554/stream`
4. Open the dashboard, paste URL into "Phone Camera URL", then click Start.

## Deployment Notes

- After deployment, the server must be able to reach the phone stream URL.
- For cloud deployments, direct phone LAN URLs usually do not work.
- Reliable options for deployed environments:
  - Run server on same LAN as phone stream source.
  - Use RTSP relay/tunnel reachable by deployed server.
  - Use USB camera bridge software that exposes a local camera to the host running this app.

## Notes

- If local camera diagnostics show no devices, use phone URL mode.
- If stream fails, check firewall rules and phone app streaming state.
