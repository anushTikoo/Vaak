from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import cart, chat, health, me, orders, voice
from src.core.config import settings
from src.core.errors import VakException, generic_exception_handler, vak_exception_handler

app = FastAPI(
    title="Vāk API",
    description="Voice-first AI conversational commerce backend for Zepto",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register exception handlers
app.add_exception_handler(VakException, vak_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Mount API routers
app.include_router(health.router)
app.include_router(me.router)
app.include_router(voice.router)
app.include_router(chat.router)
app.include_router(cart.router)
app.include_router(orders.router)

# Cloudflare Python Workers ASGI Entrypoint
try:
    from workers import asgi

    Default = asgi.entrypoint(app)
except ImportError:
    # Running outside Cloudflare Workers (e.g. local Uvicorn)
    Default = None
