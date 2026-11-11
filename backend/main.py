"""
Verix MVP — FastAPI Application Entry Point
Pharmacovigilance Case Intelligence Platform
"""

import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("verix")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Verix MVP starting up")
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY not set — analysis will fail")
    yield
    logger.info("Verix MVP shutting down")


app = FastAPI(
    title="Verix Case Intelligence API",
    description="Three-layer pharmacovigilance intelligence platform",
    version="0.1.0",
    lifespan=lifespan
)

# CORS for local React dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from backend.routers.cases import router as cases_router
app.include_router(cases_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "verix-mvp", "version": "0.1.0"}


@app.get("/ui", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
def frontend():
    """Serve the standalone frontend — no npm/build step needed."""
    html_path = Path(__file__).parent.parent / "frontend" / "standalone.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Verix</h1><p>Frontend not found. Place standalone.html in frontend/</p>", status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
