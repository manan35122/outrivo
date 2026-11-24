"""FastAPI app exposing the two graded endpoints: POST /chat and GET /health."""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from . import chat_service
from .middleware import ChatGuardMiddleware, RequestContextMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the graph and connect to Postgres in the background, so /health answers at once
    # and the first real chat does not pay the start-up cost.
    threading.Thread(target=chat_service.warm_up, daemon=True).start()
    yield


app = FastAPI(title="Outrivo Agent API", lifespan=lifespan)

# The LAST middleware added is the OUTERMOST, so a request passes through:
# CORS -> RequestContext -> ChatGuard -> route.
app.add_middleware(ChatGuardMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # the Vercel website calls this API from the browser
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


class ChatRequest(BaseModel):
    user_id: str
    thread_id: str
    message: str


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@app.post("/chat")
def chat(req: ChatRequest, request: Request) -> dict:
    # ChatGuardMiddleware has already validated the body, applied the rate limit and checked
    # the budget. run_chat never raises: failures come back as a friendly reply.
    return chat_service.run_chat(req.user_id, req.thread_id, req.message, request.state.request_id)
