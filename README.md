# Vaak (वाक्) — Voice-First AI Shopping Assistant

> **Vaak (वाक्)** is an Indian-context, voice-first AI shopping assistant designed to make digital commerce effortless through natural speech, starting with grocery ordering via Zepto.

---

## 1. Product Philosophy

- **Voice-First, Never Voice-Only**: Speech drives natural conversational discovery and cart building, while a visual interface allows users to inspect items, adjust quantities, review itemized prices, and make informed choices.
- **Explicit Confirmation**: No order is placed or purchase initiated without the user's explicit, visual confirmation.
- **Deterministic Business Logic**: The LLM extracts intents and suggests actions; the backend strictly computes prices, checks stock, and maintains authoritative cart state.
- **Multilingual Support**: Supports Indian English, Hindi, and regional Indic languages powered by Sarvam AI.

---

## 2. Monorepo Architecture

```text
vaak/
├── apps/
│   └── mobile/                # React Native + Expo SDK 58 (Expo Router, TypeScript)
│       ├── src/               # Application code, hooks, components
│       └── app.json           # Permissions and Android configuration
│
├── services/
│   └── backend/               # FastAPI + uv (Python 3.12)
│       ├── src/
│       │   ├── api/routes/    # /health, /voice, /chat, /cart, /orders, /me
│       │   ├── core/          # Config, logging, error handlers
│       │   ├── schemas/       # Pydantic v2 data models
│       │   └── services/      # Sarvam client, Zepto MCP, voice orchestrator
│       ├── tests/             # Pytest asynchronous test suite
│       └── wrangler.jsonc     # Cloudflare Python Workers configuration
│
├── docs/                      # ARCHITECTURE, SETUP, API, INTEGRATIONS, DEPLOYMENT
├── .vscode/                   # Settings, recommended extensions, launch/task configs
└── package.json               # Root monorepo scripts
```

---

## 3. Technology Stack

- **Mobile Client**: React Native 0.88, Expo SDK 58, Expo Router, TypeScript.
- **Backend Service**: Python 3.12, FastAPI, Pydantic v2, uv, Pytest.
- **Cloud Runtime**: Cloudflare Python Workers (ASGI integration).
- **Voice Intelligence**: Sarvam AI (`saaras:v4` STT, `bulbul:v4-flash` TTS, `sarvam-105b-conversations` LLM).
- **Quick Commerce**: Zepto MCP Server (`https://mcp.zepto.co.in/mcp`).
- **Database & Pooling**: Neon PostgreSQL + Cloudflare Hyperdrive.

---

## 4. Quick Start Commands

### Root Workspace Commands

```bash
# 1. Start the FastAPI backend locally (with auto-reload)
npm run backend

# 2. Run backend test suite (Pytest)
npm run test:backend

# 3. Start Expo development server for the mobile app
npm run mobile

# 4. Launch mobile app on connected Android emulator or phone
npm run android

# 5. Run TypeScript typecheck on mobile
npm run typecheck

# 6. Run linting across backend (Ruff) and mobile (ESLint)
npm run lint
```

---

## 5. Environment & Manual Setup Instructions

Please consult [docs/SETUP.md](file:///home/anushtikoo/Desktop/hackathons/scalarxwisprflow/Vaak/docs/SETUP.md) for full instructions on setting up Android Studio, Android SDK platforms, emulator, and connecting a physical Android device via USB debugging on Fedora Linux KDE.
