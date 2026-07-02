"""
SQL Agent Web Interface — FastAPI backend.

Run with:
    cd sql_cap_stone/web
    uvicorn app:app --reload --port 8000
"""

import os
import sys

# ── Path setup ────────────────────────────────────────────────────────────────
_web_dir    = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_web_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# ── Prompt manager ────────────────────────────────────────────────────────────
from prompt_manager import PromptManager

_data_dir = os.path.join(_web_dir, "data")
pm = PromptManager(data_dir=_data_dir)

# ── Patch agent's prompt function before importing agent ──────────────────────
import agent as _agent_module
_agent_module.sql_system_prompt = lambda schema, q: pm.render(schema, q)

from agent import run as run_agent, build_plotly_chart, get_llm

# ── FastAPI ───────────────────────────────────────────────────────────────────
import io
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import uvicorn

from feedback_store import FeedbackStore

app = FastAPI(title="SQL Agent", version="1.0")

_static_dir = os.path.join(_web_dir, "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

fb_store = FeedbackStore(data_dir=_data_dir)


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


class ChartRequest(BaseModel):
    dataframe_json: str
    question:       str
    sql_query:      str
    chart_type:     str


class FeedbackRequest(BaseModel):
    message_id: Optional[str] = None
    rating:     Optional[str] = None
    text:       str
    type:       str


class PromptUpdateRequest(BaseModel):
    template: str


class SuggestPromptRequest(BaseModel):
    feedback_text: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(os.path.join(_static_dir, "index.html"))


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        result = await run_in_threadpool(run_agent, req.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "question":       result.get("question",       req.message),
        "sql_query":      result.get("sql_query",      ""),
        "sql_result":     result.get("sql_result",     ""),
        "dataframe_json": result.get("dataframe_json", "[]"),
        "row_count":      result.get("row_count",      0),
        "chart_json":     result.get("chart_json",     ""),
        "chart_type":     result.get("chart_type",     ""),
        "chart_options":  result.get("chart_options",  []),
        "chart_reason":   result.get("chart_reason",   ""),
        "interpretation": result.get("interpretation", ""),
        "error":          result.get("error",          ""),
    }


@app.post("/api/chart")
async def regenerate_chart(req: ChartRequest):
    """Re-render a chart for the given dataframe with a different chart type."""
    try:
        df = pd.read_json(io.StringIO(req.dataframe_json))
        chart_json = await run_in_threadpool(
            build_plotly_chart, df, req.question, req.chart_type
        )
        return {"chart_json": chart_json}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/system-prompt")
async def get_system_prompt():
    return {"template": pm.get_template(), "history": pm.get_history()}


@app.put("/api/system-prompt")
async def update_system_prompt(req: PromptUpdateRequest):
    if not req.template.strip():
        raise HTTPException(status_code=400, detail="Template cannot be empty")
    pm.save_template(req.template)
    return {"status": "ok", "template": req.template}


@app.post("/api/system-prompt/suggest")
async def suggest_prompt(req: SuggestPromptRequest):
    if not req.feedback_text.strip():
        raise HTTPException(status_code=400, detail="feedback_text is required")
    try:
        suggestion = await run_in_threadpool(pm.suggest_from_feedback, req.feedback_text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"suggestion": suggestion}


@app.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest):
    fb_id = fb_store.add(req.model_dump())
    return {"status": "ok", "id": fb_id}


@app.get("/api/feedback")
async def get_feedback():
    return {"feedback": fb_store.get_all()}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
