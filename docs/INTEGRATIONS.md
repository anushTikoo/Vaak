# Vāk (वाक्) — External Integrations & Providers

This document details the technical specifications, security models, and known limitations of Vāk's external integrations.

---

## 1. Sarvam AI (Voice & Indic Intelligence)

Sarvam provides speech-to-text, text-to-speech, and conversational reasoning tailored for Indian languages and accents.

### A. Speech-to-Text (STT)
- **Model**: `saaras:v4`
- **Real-Time Streaming Endpoint**: `wss://api.sarvam.ai/speech-to-text-realtime/ws`
- **Features**: Automatic language detection across 10+ Indic languages + Indian English, low-latency chunk streaming.
- **Provider Interface**: `src/services/sarvam/client.py -> transcribe_audio()`

### B. Text-to-Speech (TTS)
- **Model**: `bulbul:v4-flash`
- **Streaming Endpoint**: `wss://api.sarvam.ai/text-to-speech/ws`
- **Provider Interface**: `src/services/sarvam/client.py -> generate_speech()`

### C. Conversational LLM
- **Primary Model**: `sarvam-105b-conversations`
- **Fallback / Evaluation Model**: `sarvam-105b`
- **Role**: Tool/function calling for product search and cart modification.
- **Rule**: The LLM NEVER mutates order status or final financial commitments directly. Tool calls are strictly intercepted and validated by backend business rules.

---

## 2. Zepto MCP (Quick Commerce Integration)

### A. Official Specification
- **Repository**: [https://github.com/zeptonow/mcp](https://github.com/zeptonow/mcp)
- **Hosted MCP Endpoint**: `https://mcp.zepto.co.in/mcp`

### B. Authentication & OAuth Protocol
- Zepto authentication uses an OAuth flow with phone number verification and OTP.
- **Security Invariant**: Never expose user OAuth tokens, client secrets, or session cookies to the mobile client. All tokens are securely encrypted and persisted on the backend (PostgreSQL).
- During initial interactive authorization, the backend will coordinate with the developer to supply the OTP.

### C. Critical Known Uncertainty & Mitigation: Cart Synchronization
Investigated GitHub issues on Zepto MCP:
1. **Issue #62 & #74**: Items added to the MCP cart do not always reflect immediately in the native Zepto mobile application cart.
2. **Issue #21**: Session/cart scoping differences between MCP API clients and consumer app authentication tokens.

**Vāk Architectural Solution**:
- Vāk maintains its own authoritative **in-memory & PostgreSQL-backed shopping cart** (`Cart` & `CartItem` schemas).
- The user reviews, modifies quantities, and visually confirms the Vāk cart.
- When the order confirmation step occurs, Vāk executes the MCP order placement workflow with atomic confirmation.
- We do not assume synchronous reflection in the consumer Zepto app's native UI until the order is officially confirmed by the Zepto backend.

---

## 3. Database & Connectivity (Neon PostgreSQL + Hyperdrive)

- **Database**: Neon Serverless PostgreSQL.
- **Connection**: Cloudflare Hyperdrive connection pooling for edge Python Workers.
- **Driver**: `asyncpg` with fallback to connection pooling.
- **Security**: No payment card numbers, CVVs, or UPI PINs are ever stored.
