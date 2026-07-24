"""
Call History API.

GET /calls/history — returns all call sessions with conversation.
GET /calls/history/{call_sid} — returns a single call with full conversation.
"""
import logging
from datetime import datetime
from fastapi import APIRouter
import boto3

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
table = dynamodb.Table(settings.DYNAMODB_SESSION_TABLE)


@router.get("/history")
async def get_call_history():
    """Get all call history with conversation from DynamoDB."""
    try:
        response = table.scan()
        items = response.get("Items", [])

        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))

        calls = []
        for item in items:
            session_data = item.get("session_data", {})
            started_at = session_data.get("started_at", 0)

            # Format timestamp
            started_time = ""
            if started_at:
                try:
                    started_time = datetime.fromtimestamp(int(started_at)).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    started_time = str(started_at)

            calls.append({
                "call_sid": item.get("call_sid"),
                "status": item.get("status", "active"),
                "user_phone": session_data.get("user_phone", ""),
                "from_number": session_data.get("from_number", ""),
                "to_number": session_data.get("to_number", ""),
                "direction": session_data.get("direction", ""),
                "dialect": session_data.get("dialect", ""),
                "step": session_data.get("step", ""),
                "crop": session_data.get("crop", ""),
                "wants_cytoboost": session_data.get("wants_cytoboost", ""),
                "wants_pump": session_data.get("wants_pump", ""),
                "wants_tarpaulin": session_data.get("wants_tarpaulin", ""),
                "address": session_data.get("address", ""),
                "started_at": started_time,
                "conversation": session_data.get("conversation", []),
            })

        calls.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return {"total": len(calls), "calls": calls}

    except Exception as e:
        logger.error(f"[CALL HISTORY] Error: {e}")
        return {"error": str(e)}, 500


@router.get("/history/{call_sid}")
async def get_call_detail(call_sid: str):
    """Get full details and conversation for a specific call."""
    try:
        response = table.get_item(Key={"call_sid": call_sid})
        item = response.get("Item")

        if not item:
            return {"error": "Call not found"}, 404

        session_data = item.get("session_data", {})
        started_at = session_data.get("started_at", 0)
        started_time = ""
        if started_at:
            try:
                started_time = datetime.fromtimestamp(int(started_at)).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                started_time = str(started_at)

        return {
            "call_sid": item.get("call_sid"),
            "status": item.get("status", "active"),
            "user_phone": session_data.get("user_phone", ""),
            "direction": session_data.get("direction", ""),
            "dialect": session_data.get("dialect", ""),
            "started_at": started_time,
            "crop": session_data.get("crop", ""),
            "wants_cytoboost": session_data.get("wants_cytoboost", ""),
            "wants_pump": session_data.get("wants_pump", ""),
            "wants_tarpaulin": session_data.get("wants_tarpaulin", ""),
            "address": session_data.get("address", ""),
            "conversation": session_data.get("conversation", []),
        }

    except Exception as e:
        logger.error(f"[CALL DETAIL] Error: {e}")
        return {"error": str(e)}, 500
