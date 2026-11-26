# Vaak (वाक्) — System Architecture

## 1. High-Level System Architecture

```text
              Vaak Mobile App
       (React Native + Expo SDK 58)
                    │
            HTTPS / WebSocket
                    │
                    ▼
        Cloudflare Python Worker
                (FastAPI)
                    │
      ┌─────────────┼─────────────┐
      │             │             │
      ▼             ▼             ▼
   Sarvam       Zepto MCP       Neon
    APIs        (Catalog/     PostgreSQL
 (STT/TTS/LLM)    Cart)       (via Hyperdrive)
```

## 2. Core Tenets

1. **Voice-First, Not Voice-Only**:
   - The user commands the application naturally using voice (English, Hindi, Indic languages).
   - Audio feedback is streamed back for a hands-free experience.
   - The UI continuously visualizes cart state, quantities, unit prices, product cards, and total amounts.
   - **Mandatory Visual Review**: No order is placed or purchase initiated without explicit, unambiguous user confirmation on the visual interface.

2. **Zero Deterministic Decisions in LLMs**:
   - Conversational LLM (Sarvam `sarvam-105b-conversations`) extracts intent and issues structured tool calls.
   - All financial logic, price calculations, cart quantity constraints, and order state machines are enforced deterministically in the FastAPI backend.

3. **Strict Credential & Network Isolation**:
   - The mobile application connects solely to the Vaak backend.
   - Zero API keys (Sarvam), database strings (Neon), or merchant tokens (Zepto OAuth) ever touch the mobile client.

## 3. Directory Structure

```text
vaak/
├── apps/
│   └── mobile/                # React Native / Expo application
│       ├── app/               # Expo Router file-based routes
│       │   ├── (auth)/        # Authentication screens
│       │   ├── (tabs)/        # Tab navigation (Voice HUD, Cart, Orders, Profile)
│       │   ├── cart/          # Checkout & review
│       │   └── _layout.tsx    # Root layout & providers
│       ├── src/               # Application code (components, hooks, services, stores)
│       └── app.json           # Expo & Android permissions config
│
├── services/
│   └── backend/               # FastAPI backend for Cloudflare Python Workers
│       ├── src/
│       │   ├── api/routes/    # Endpoints (/health, /voice, /chat, /cart, /orders, /me)
│       │   ├── core/          # Config (Pydantic), logging, custom error handlers
│       │   ├── schemas/       # Pydantic v2 data models
│       │   └── services/      # Sarvam, Zepto MCP, and Voice Orchestrator
│       ├── tests/             # Pytest asynchronous test suite
│       ├── wrangler.jsonc     # Cloudflare Worker configuration
│       └── pyproject.toml     # Managed via uv (Python 3.12)
│
├── docs/                      # Architectural, setup, API & integration specifications
├── .vscode/                   # Pre-configured tasks, launch profiles, recommended extensions
└── package.json               # Root monorepo workspace scripts
```
