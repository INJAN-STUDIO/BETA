# Project B.E.T.A Plan: Cloud Mobile Migration (Modular/Lego Architecture)

## Objective
Migrate the AI Chatbot (BETA) to a cloud-hosted platform, featuring a custom, modular, "Lego-style" architecture that allows for seamless feature expansion.

## Phase 1: The Core (Foundation)
- [x] Clean up `requirements.txt`: FastAPI, Uvicorn, httpx, python-dotenv.
- [x] Initialize FastAPI backend: Structured for modularity (routes, services, tools).
- [x] Implement Core Chat: Connect to Groq API (switched to llama-3.3-70b-versatile).
- [x] Setup `static/` directory: "Claude-style" minimal dark UI.
- [x] Memory Implementation: Added persistent history via `chat_history.json`.

## Phase 2: Modular Expansion
- [x] Research Module: Added Serper API search integration (configured in .env).
- [ ] Multi-modal Module: Add vision and file upload support.
- [ ] Voice Module: Integrate Web Speech API (Browser-native).

## Phase 3: Cloud Deployment & Polish
- [ ] Containerization: Dockerize the modular app (optional but recommended).
- [x] Deployment: Currently hosted on Render (Need to update env vars on dashboard).
- [x] Final Branding: Fixed header alignment, sidebar z-index, and added animated thinking dots.

---
Status: ACTIVE (Modular/Lego Architecture Design)
Last Updated: 2026-08-11
