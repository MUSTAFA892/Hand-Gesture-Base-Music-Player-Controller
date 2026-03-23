# Hand Gesture Controlled Media Player (FastAPI)

Control Linux system media using webcam hand gestures.

## Features

- FastAPI backend with realtime WebSocket status
- Hand gesture recognition via OpenCV + MediaPipe
- Controls system media and audio using `playerctl` and `pactl`
- Modern web dashboard for status and manual control

## Gesture Mapping

- `OPEN_PALM` -> Play/Pause
- `THUMB_UP` -> Volume Up
- `THUMB_DOWN` -> Volume Down
- `V_SIGN` -> Next Track
- `FIST` -> Previous Track
- `PINCH` -> Mute Toggle

## Requirements

- Linux desktop with webcam
- Python 3.10+
- `playerctl`
- `pactl` (PulseAudio/PipeWire compatibility layer)

Install Linux packages (Ubuntu/Debian example):

```bash
sudo apt update
sudo apt install -y playerctl pulseaudio-utils v4l-utils
```

## Setup

```bash
cd /home/mustafa/PROJECTS/Hand-Gesture-controlled-Music-player
python3 -m venv .venv
source .venv/bin/activate
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

## Notes

- The app uses webcam index `0` by default.
- If no media player supports MPRIS, `playerctl` actions will fail.
- System volume control is applied to default sink via `pactl`.
