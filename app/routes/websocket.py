"""
app/routes/websocket.py

Real-time WebSocket layer for instant notifications and live updates.

Architecture:
  - Single endpoint: GET /ws (upgraded to WebSocket)
  - Auth: reads session cookie just like HTTP routes
  - Manager: dict[user_id] -> set[WebSocket]
  - Multiple connections per user supported (multiple tabs)

Events sent to clients (JSON):
  {"type": "notification", "data": {...}}
  {"type": "task_updated", "data": {"task_id": 1, "project_id": 2}}
  {"type": "task_assigned", "data": {...}}
  {"type": "presence", "data": {"online_user_ids": [1, 2, 3]}}
  {"type": "pong"}

Events received from clients:
  {"type": "ping"}
  {"type": "presence_request"}
"""
import json
import asyncio
from typing import Dict, Set, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import User


router = APIRouter(tags=["websocket"])


# ============================================================
# Connection Manager
# ============================================================

class ConnectionManager:
    """
    Tracks all active WebSocket connections per user.
    A single user can have multiple connections (multiple tabs / devices).
    """
    def __init__(self):
        # user_id -> set of WebSocket connections
        self.active: Dict[int, Set[WebSocket]] = {}

    async def connect(self, ws: WebSocket, user_id: int):
        """Register a new connection for this user."""
        await ws.accept()
        if user_id not in self.active:
            self.active[user_id] = set()
        self.active[user_id].add(ws)
        # Note: we DON'T broadcast presence here.
        # The endpoint sends the 'connected' message first, then broadcasts presence.

    def disconnect(self, ws: WebSocket, user_id: int):
        """Remove a connection. Called on disconnect."""
        if user_id in self.active:
            self.active[user_id].discard(ws)
            if not self.active[user_id]:
                del self.active[user_id]

    def online_user_ids(self) -> list:
        """List of user_ids currently connected."""
        return list(self.active.keys())

    def is_online(self, user_id: int) -> bool:
        return user_id in self.active and len(self.active[user_id]) > 0

    async def send_to_user(self, user_id: int, message: dict):
        """Send a JSON message to ALL connections of a single user."""
        if user_id not in self.active:
            return  # User not online — they'll see it on next page load
        text = json.dumps(message)
        dead_connections = []
        for ws in self.active[user_id]:
            try:
                await ws.send_text(text)
            except Exception:
                dead_connections.append(ws)
        # Clean up dead connections
        for ws in dead_connections:
            self.active[user_id].discard(ws)
        if not self.active.get(user_id):
            self.active.pop(user_id, None)

    async def send_to_users(self, user_ids: list, message: dict):
        """Send the same message to multiple users."""
        for uid in user_ids:
            await self.send_to_user(uid, message)

    async def broadcast(self, message: dict, exclude_user_id: Optional[int] = None):
        """Send to ALL connected users (e.g. for presence updates)."""
        text = json.dumps(message)
        for uid, sockets in list(self.active.items()):
            if uid == exclude_user_id:
                continue
            dead = []
            for ws in sockets:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                sockets.discard(ws)

    async def broadcast_presence(self):
        """Tell all clients who is currently online."""
        await self.broadcast({
            "type": "presence",
            "data": {"online_user_ids": self.online_user_ids()},
        })


# Singleton manager — imported by other modules to push events
manager = ConnectionManager()


# ============================================================
# WebSocket endpoint
# ============================================================

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    Single WebSocket endpoint. Auth via session cookie.

    Client side (JS):
        const ws = new WebSocket(`ws://${location.host}/ws`);
        ws.onmessage = (e) => { const msg = JSON.parse(e.data); ... }
    """
    # ---- Authenticate from session cookie ----
    # The Starlette SessionMiddleware decodes the cookie into ws.session
    user_id = None
    try:
        if "session" in ws.scope:
            user_id = ws.scope["session"].get("user_id")
    except Exception:
        pass

    if not user_id:
        await ws.close(code=4401)  # custom code = unauthorized
        return

    # Verify user still exists in DB
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            await ws.close(code=4401)
            return
    finally:
        db.close()

    # ---- Accept connection ----
    await manager.connect(ws, user_id)

    try:
        # Send initial 'connected' message FIRST so client knows we're authed
        await ws.send_text(json.dumps({
            "type": "connected",
            "data": {"user_id": user_id, "online_user_ids": manager.online_user_ids()},
        }))

        # Now broadcast updated presence to OTHER users (not this one)
        await manager.broadcast({
            "type": "presence",
            "data": {"online_user_ids": manager.online_user_ids()},
        }, exclude_user_id=user_id)

        # ---- Listen loop ----
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")
            if mtype == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            elif mtype == "presence_request":
                await ws.send_text(json.dumps({
                    "type": "presence",
                    "data": {"online_user_ids": manager.online_user_ids()},
                }))
            # add more client->server message types here as needed

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws] Error for user {user_id}: {e}")
    finally:
        manager.disconnect(ws, user_id)
        await manager.broadcast_presence()


# ============================================================
# Helper functions other routes call to push events
# ============================================================

async def push_notification(user_id: int, notification_dict: dict):
    """Push a new notification to one user in real-time."""
    await manager.send_to_user(user_id, {
        "type": "notification",
        "data": notification_dict,
    })


async def push_task_updated(user_ids: list, task_id: int, project_id: int, updated_by: str):
    """Tell users that a task was updated (so their open pages refresh)."""
    await manager.send_to_users(user_ids, {
        "type": "task_updated",
        "data": {
            "task_id": task_id,
            "project_id": project_id,
            "updated_by": updated_by,
        },
    })


async def push_task_assigned(user_id: int, task_id: int, project_id: int, task_description: str):
    """Tell a user they were just assigned to a task."""
    await manager.send_to_user(user_id, {
        "type": "task_assigned",
        "data": {
            "task_id": task_id,
            "project_id": project_id,
            "task_description": task_description,
        },
    })


# ----- Synchronous bridges for use inside sync DB routes -----
def push_notification_sync(user_id: int, notification_dict: dict):
    """Sync wrapper — call from anywhere without await."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(push_notification(user_id, notification_dict))
        else:
            loop.run_until_complete(push_notification(user_id, notification_dict))
    except RuntimeError:
        # No event loop in this thread — just skip the realtime push
        # (the notification is still saved in DB, user will see on next page load)
        pass
    except Exception as e:
        print(f"[ws] push_notification_sync failed: {e}")


def push_task_updated_sync(user_ids: list, task_id: int, project_id: int, updated_by: str):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(push_task_updated(user_ids, task_id, project_id, updated_by))
    except Exception as e:
        print(f"[ws] push_task_updated_sync failed: {e}")