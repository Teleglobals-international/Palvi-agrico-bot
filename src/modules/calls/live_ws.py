"""
Live Call WebSocket Endpoint — Frontend subscribes here to receive
real-time conversation updates for a specific call.

Endpoint: /ws/live/{call_sid}

Messages sent to client:
- {"type": "status", "status": "started"|"ended", "call_sid": "..."}
- {"type": "turn", "role": "bot"|"farmer", "text": "...", "step": "...", "timestamp": ...}
- {"type": "history", "turns": [...]}  (sent on connect for late joiners)
"""
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.modules.calls.live_broadcast import broadcaster

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/live/{call_sid}")
async def live_call_ws(websocket: WebSocket, call_sid: str):
    """WebSocket endpoint for live call conversation streaming.

    Frontend connects here after initiating a call to receive real-time
    conversation updates as the bot and farmer speak.
    """
    await websocket.accept()
    logger.info(f"[LIVE WS] Frontend connected for call: {call_sid}")

    # Send existing conversation history (for late joiners)
    history = broadcaster.get_history(call_sid)
    if history:
        await websocket.send_text(json.dumps({
            "type": "history",
            "turns": history,
        }))

    # Subscribe to live updates
    broadcaster.subscribe(call_sid, websocket)

    try:
        # Keep connection alive — listen for client pings/close
        while True:
            # Client can send "ping" to keep alive, or we just wait for disconnect
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        logger.info(f"[LIVE WS] Frontend disconnected from call: {call_sid}")
    except Exception as e:
        logger.error(f"[LIVE WS] Error: {e}")
    finally:
        broadcaster.unsubscribe(call_sid, websocket)
