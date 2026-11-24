
"""FastAPI app exposing the Outrivo agent and leads API."""

import logging
import re
import threading
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import Response

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from psycopg.errors import UniqueViolation

from . import chat_service
from .db import get_pool
from .middleware import ChatGuardMiddleware, RequestContextMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

LeadStage = Literal["new", "contacted", "replied", "meeting", "won", "lost"]

ID_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{1,128}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=chat_service.warm_up, daemon=True).start()
    yield


app = FastAPI(title="Outrivo Agent API", lifespan=lifespan)

app.add_middleware(ChatGuardMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

class ChatRequest(BaseModel):
    user_id: str
    thread_id: str
    message: str


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    source: str | None = Field(default="manual", max_length=80)
    stage: LeadStage = "new"
    notes: str | None = Field(default=None, max_length=2000)


class LeadUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    source: str | None = Field(default=None, max_length=80)
    stage: LeadStage | None = None
    notes: str | None = Field(default=None, max_length=2000)


# ------------------------------------------------------------------
# User identification
# ------------------------------------------------------------------

def get_user_id(
    x_user_id: str = Header(..., alias="X-User-ID"),
) -> str:
    if not ID_PATTERN.fullmatch(x_user_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid user ID.",
        )
    return x_user_id


# ------------------------------------------------------------------
# Existing required endpoints
# ------------------------------------------------------------------

@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"

@app.head("/health")
async def health_head():
    return Response(status_code=200)


@app.post("/chat")
def chat(req: ChatRequest, request: Request) -> dict:
    return chat_service.run_chat(
        req.user_id,
        req.thread_id,
        req.message,
        request.state.request_id,
    )


# ------------------------------------------------------------------
# Leads API
# ------------------------------------------------------------------

@app.get("/leads")
def list_leads(
    user_id: str = Depends(get_user_id),
    stage: LeadStage | None = None,
    search: str | None = Query(default=None, max_length=100),
):
    conditions = ["user_id = %s"]
    params: list = [user_id]

    if stage:
        conditions.append("stage = %s")
        params.append(stage)

    if search and search.strip():
        conditions.append(
            "(name ILIKE %s OR company ILIKE %s OR email ILIKE %s "
            "OR industry ILIKE %s OR city ILIKE %s)"
        )
        term = f"%{search.strip()}%"
        params.extend([term] * 5)

    sql = f"""
        SELECT id, name, company, industry, city, email, phone,
               source, stage, notes, created_at, updated_at
        FROM leads
        WHERE {" AND ".join(conditions)}
        ORDER BY updated_at DESC, id DESC
        LIMIT 200
    """

    with get_pool().connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return {"total": len(rows), "leads": rows}


@app.post("/leads", status_code=201)
def create_lead(
    lead: LeadCreate,
    user_id: str = Depends(get_user_id),
):
    if not lead.name.strip():
        raise HTTPException(status_code=422, detail="Lead name cannot be empty.")

    try:
        with get_pool().connection() as conn:
            row = conn.execute(
                """
                INSERT INTO leads (
                    user_id, name, company, industry, city,
                    email, phone, source, stage, notes
                )
                VALUES (
                    %(user_id)s, %(name)s, %(company)s, %(industry)s,
                    %(city)s, %(email)s, %(phone)s, %(source)s,
                    %(stage)s, %(notes)s
                )
                RETURNING id, name, company, industry, city, email,
                          phone, source, stage, notes, created_at, updated_at
                """,
                {"user_id": user_id, **lead.model_dump()},
            ).fetchone()

    except UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="A lead with this email already exists.",
        )

    return {"lead": row}


@app.patch("/leads/{lead_id}")
def update_lead(
    lead_id: int,
    updates: LeadUpdate,
    user_id: str = Depends(get_user_id),
):
    changes = updates.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update.",
        )

    if "name" in changes and (
        changes["name"] is None or not changes["name"].strip()
    ):
        raise HTTPException(
            status_code=422,
            detail="Lead name cannot be empty.",
        )

    allowed_fields = {
        "name", "company", "industry", "city", "email",
        "phone", "source", "stage", "notes",
    }

    if not set(changes).issubset(allowed_fields):
        raise HTTPException(status_code=400, detail="Invalid fields.")

    assignments = [f"{field} = %s" for field in changes]
    values = list(changes.values())

    sql = f"""
        UPDATE leads
        SET {", ".join(assignments)}, updated_at = now()
        WHERE id = %s AND user_id = %s
        RETURNING id, name, company, industry, city, email,
                  phone, source, stage, notes, created_at, updated_at
    """

    try:
        with get_pool().connection() as conn:
            row = conn.execute(
                sql,
                [*values, lead_id, user_id],
            ).fetchone()
    except UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="A lead with this email already exists.",
        )

    if not row:
        raise HTTPException(status_code=404, detail="Lead not found.")

    return {"lead": row}


@app.delete("/leads/{lead_id}")
def delete_lead(
    lead_id: int,
    user_id: str = Depends(get_user_id),
):
    with get_pool().connection() as conn:
        row = conn.execute(
            """
            DELETE FROM leads
            WHERE id = %s AND user_id = %s
            RETURNING id
            """,
            (lead_id, user_id),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Lead not found.")

    return {"deleted": True, "lead_id": row["id"]}
