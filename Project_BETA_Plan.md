# Project B.E.T.A Plan: Cloud Mobile Migration (Modular/Lego Architecture)

## Objective
Migrate the AI Chatbot (BETA) to a cloud-hosted platform, featuring a custom, modular, "Lego-style" architecture that allows for seamless feature expansion.

## Phase 1: The Core (Foundation)
- [x] Clean up `requirements.txt`: FastAPI, Uvicorn, httpx, python-dotenv.
- [ ] Initialize FastAPI backend: Structured for modularity (routes, services, tools).
- [ ] Implement Core Chat: Connect to Groq API for base text interaction.
- [ ] Setup `static/` directory: "Claude-style" minimal dark UI.

## Phase 2: Modular Expansion
- [ ] Research Module: Add a pluggable search tool (Tavily/Serper).
- [ ] Multi-modal Module: Add vision and file upload support.
- [ ] Voice Module: Integrate Web Speech API (Browser-native).

## Phase 3: Cloud Deployment & Polish
- [ ] Containerization: Dockerize the modular app.
- [ ] Deployment: Host on Render.
- [ ] Final Branding: Apply custom cyberpunk theme/assets.

---
Status: ACTIVE (Modular/Lego Architecture Design)
Last Updated: 2026-08-08
