from uuid import UUID

from fastapi import APIRouter

from src.schemas.chat import ChatMessageRequest, ChatMessageResponse
from src.services.voice.orchestrator import voice_orchestrator

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


@router.post("/message", response_model=ChatMessageResponse)
async def send_chat_message(request: ChatMessageRequest):
    return await voice_orchestrator.process_user_intent(
        user_message=request.message,
        session_id=request.session_id,
        language=request.language,
        generate_audio=request.generate_audio,
    )


@router.get("/history/{session_id}")
async def get_chat_history(session_id: UUID):
    """Retrieve recent conversational memory turns for a session."""
    turns = voice_orchestrator.get_session_history(session_id)
    return {"session_id": session_id, "turns": turns, "count": len(turns)}


@router.delete("/history/{session_id}")
async def clear_chat_history(session_id: UUID):
    """Clear conversational memory for a session."""
    voice_orchestrator.clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}

