import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
from app.api.auth import router as auth_router
from app.api.projects import router as projects_router
from app.api.documents import router as documents_router
from app.api.integrations import router as integrations_router
from app.api.search import router as search_router
from app.api.chat import router as chat_router
from app.api.memory import router as memory_router
from app.api.team import router as team_router
from app.api.obligations import router as obligations_router
from app.api.clause_comparison import router as clause_comparison_router
from app.api.folder_mappings import router as folder_mappings_router

app = FastAPI(title="Rastro API", version="0.7.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(team_router, prefix="/api/v1")
app.include_router(obligations_router, prefix="/api/v1")
app.include_router(clause_comparison_router, prefix="/api/v1")
app.include_router(folder_mappings_router, prefix="/api/v1")


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "rastro-api", "version": "0.7.0"}
