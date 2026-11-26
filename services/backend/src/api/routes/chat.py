from fastapi import APIRouter

from src.schemas.chat import ChatMessageRequest, ChatMessageResponse
from src.services.voice.orchestrator import voice_orchestrator

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


@router.post("/message", response_model=ChatMessageResponse)
async def send_chat_message(request: ChatMessageRequest):
    return await voice_orchestrator.process_user_intent(
        user_message=request.message,
        session_id=request.session_id,
    )
