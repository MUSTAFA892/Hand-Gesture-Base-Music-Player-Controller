from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.services.gesture_service import GestureService
from app.services.media_controller import MediaController

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Hand Gesture Controlled Media Player", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

media_controller = MediaController()
gesture_service = GestureService(action_callback=media_controller.execute_action)


@app.on_event("shutdown")
def shutdown_event() -> None:
    gesture_service.stop()


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "Hand Gesture Controlled Media Player",
        },
    )


@app.get("/api/status")
def get_status() -> JSONResponse:
    return JSONResponse(
        {
            "gesture": gesture_service.get_status(),
            "audio": media_controller.get_audio_state(),
        }
    )


@app.post("/api/gesture/start")
def start_gesture_service(camera_index: int = 0) -> JSONResponse:
    return JSONResponse(gesture_service.start(camera_index=camera_index))


@app.get("/api/cameras")
def get_cameras() -> JSONResponse:
    return JSONResponse({"available_cameras": gesture_service.list_available_cameras()})


@app.post("/api/gesture/stop")
def stop_gesture_service() -> JSONResponse:
    return JSONResponse(gesture_service.stop())


@app.post("/api/media/{action}")
def execute_media_action(action: str) -> JSONResponse:
    result = media_controller.execute_action(action)
    return JSONResponse(result)


@app.websocket("/ws/status")
async def websocket_status(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            payload: dict[str, Any] = {
                "gesture": gesture_service.get_status(),
                "audio": media_controller.get_audio_state(),
            }
            await ws.send_json(payload)
            await asyncio.sleep(0.7)
    except WebSocketDisconnect:
        return
