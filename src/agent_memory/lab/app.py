"""FastAPI application for the Memory Lab UI."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

try:
    from fastapi.templating import Jinja2Templates
except ImportError:  # pragma: no cover - exercised when lab extras are absent
    Jinja2Templates = None  # type: ignore[assignment]

from agent_memory.lab.schemas import (
    ConsentGrantRequest,
    ConsentRevokeRequest,
    ConversationSimulationRequest,
    ConversationSimulationResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from agent_memory.lab.services import LabServices

# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: initialize and shutdown services."""
    from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

    backend_mode = os.environ.get("AGENT_MEMORY_LAB_BACKEND", "postgres")
    if backend_mode == "in-memory":
        from agent_memory.providers.in_memory_backend import InMemoryBackend

        backend = InMemoryBackend()
    else:
        try:
            from agent_memory.config import load_config
            from agent_memory.postgres.backend import PostgresBackend

            backend = PostgresBackend(load_config())
        except ModuleNotFoundError:
            from agent_memory.providers.in_memory_backend import InMemoryBackend

            backend = InMemoryBackend()
    await backend.initialize()
    app.state.services = LabServices(backend=backend, extractor=RuleBasedExtractor())
    yield
    # Shutdown
    if hasattr(app.state.services, "backend") and app.state.services.backend is not None:
        try:
            await app.state.services.backend.close()
        except Exception:
            pass


# ── App ──────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="Agent Memory Lab",
    description="Web UI for the agent-memory system",
    version="0.0.1",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="src/agent_memory/lab/static"), name="static")


class _MissingTemplateRenderer:
    """Fail clearly when lab template extras are missing.

    Importing the package should not explode during unit-test collection. The
    failure belongs to the HTML endpoint invocation, with a message telling the
    operator how to install the optional lab dependencies.
    """

    def TemplateResponse(self, *args, **kwargs):  # noqa: N802 - match Starlette API
        return HTMLResponse(
            "Memory Lab HTML templates require: pip install 'agent-memory[lab]'",
            status_code=status.HTTP_200_OK,
        )


# Setup templates
templates = (
    Jinja2Templates(directory="src/agent_memory/lab/templates")
    if Jinja2Templates is not None
    else _MissingTemplateRenderer()
)


# ── Dependencies ─────────────────────────────────────────────────────────────


async def get_services(request: Request) -> LabServices:
    """Get LabServices from request state."""
    return request.app.state.services


# ── Dashboard ────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, services: LabServices = Depends(get_services)):
    """Main dashboard with stats."""
    stats = await services.get_stats()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"stats": stats},
    )


# ── Conversation Simulation ─────────────────────────────────────────────────


@app.get("/conversation", response_class=HTMLResponse)
async def conversation_page(request: Request):
    """Conversation simulation page."""
    return templates.TemplateResponse(
        request=request,
        name="conversation.html",
    )


@app.post("/conversation/simulate")
async def simulate_conversation(
    data: ConversationSimulationRequest,
    services: LabServices = Depends(get_services),
) -> ConversationSimulationResponse:
    """Simulate a conversation and extract memories."""
    result = await services.simulate_conversation(
        messages=data.messages,
        agent_id=data.agent_id,
    )
    return ConversationSimulationResponse(**result)


# ── Extraction ──────────────────────────────────────────────────────────────


@app.get("/extract", response_class=HTMLResponse)
async def extract_page(request: Request):
    """Extraction results page."""
    return templates.TemplateResponse(
        request=request,
        name="extract.html",
    )


# ── Retrieval ───────────────────────────────────────────────────────────────


@app.get("/retrieve", response_class=HTMLResponse)
async def retrieve_page(request: Request):
    """Retrieval search page."""
    return templates.TemplateResponse(
        request=request,
        name="retrieve.html",
    )


@app.post("/retrieve/search")
async def search_memory(
    data: RetrieveRequest,
    services: LabServices = Depends(get_services),
) -> RetrieveResponse:
    """Execute retrieval search."""
    result = await services.run_retrieval(
        query=data.query,
        subject_id=data.subject_id,
        memory_types=data.memory_types,
        max_tokens=data.max_tokens,
    )
    return RetrieveResponse(**result)


# ── Consent Management ─────────────────────────────────────────────────────


@app.get("/consent", response_class=HTMLResponse)
async def consent_page(request: Request):
    """Consent management page."""
    return templates.TemplateResponse(
        request=request,
        name="consent.html",
    )


@app.post("/consent/grant")
async def grant_consent(
    data: ConsentGrantRequest,
    services: LabServices = Depends(get_services),
) -> JSONResponse:
    """Grant consent for a subject."""
    success = await services.grant_consent(
        subject_id=data.subject_id,
        memory_types=data.memory_types,
        sensitivity=data.sensitivity,
    )
    if success:
        return JSONResponse(
            content={"message": "Consent granted"},
            status_code=status.HTTP_200_OK,
        )
    return JSONResponse(
        content={"error": "Failed to grant consent"},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.post("/consent/revoke")
async def revoke_consent(
    data: ConsentRevokeRequest,
    services: LabServices = Depends(get_services),
) -> JSONResponse:
    """Revoke consent for a subject."""
    success = await services.revoke_consent(
        subject_id=data.subject_id,
        memory_type=data.memory_type,
    )
    if success:
        return JSONResponse(
            content={"message": "Consent revoked"},
            status_code=status.HTTP_200_OK,
        )
    return JSONResponse(
        content={"error": "Failed to revoke consent"},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# ── Audit Log ───────────────────────────────────────────────────────────────


@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request):
    """View audit log page."""
    return templates.TemplateResponse(
        request=request,
        name="audit.html",
    )


# ── Health Check ────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.0.1"}
