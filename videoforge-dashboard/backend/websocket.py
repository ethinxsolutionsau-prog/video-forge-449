"""WebSocket connection manager for progress updates."""
from typing import Dict, List
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, job_id: str, websocket: WebSocket):
        await websocket.accept()
        if job_id not in self.connections:
            self.connections[job_id] = []
        self.connections[job_id].append(websocket)

    def disconnect(self, job_id: str, websocket: WebSocket):
        if job_id in self.connections:
            self.connections[job_id] = [w for w in self.connections[job_id] if w != websocket]

    async def send_progress(self, job_id: str, stage: str, status: str, progress: int, message: str):
        payload = {"stage": stage, "status": status, "progress": progress, "message": message}
        await self._broadcast(job_id, payload)

    async def send_complete(self, job_id: str, download_url: str):
        payload = {"status": "complete", "download_url": download_url}
        await self._broadcast(job_id, payload)

    async def send_error(self, job_id: str, message: str):
        payload = {"status": "error", "message": message}
        await self._broadcast(job_id, payload)

    async def _broadcast(self, job_id: str, payload: dict):
        if job_id not in self.connections:
            return
        dead = []
        for ws in self.connections[job_id]:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(job_id, ws)


ws_manager = WebSocketManager()
