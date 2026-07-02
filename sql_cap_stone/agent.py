"""
Single-node SQL Agent with internal retry loop.

Graph: START -> sql_analyst -> END

The node handles everything internally:
  guard (schema question?) -> generate SQL -> execute -> [retry on error] ->
  decide visualization -> visualize? -> interpret
"""

import io
import os
import re
import sys
from typing import TypedDict, Annotated

import pandas as pd
from sqlalchemy import create_engine, text
from langchain_ollama import OllamaLLM
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import AIMessage, AnyMessage
from langsmith import traceable
from dotenv import load_dotenv
from schema_inspector import get_schema
from sql_Agent_prompt import sql_system_prompt, sql_retry_prompt
from Guard_Rails import check_sql_query

load_dotenv()

MAX_RETRIES = 100
CHART_TYPES = ["bar", "line", "scatter", "pie", "histogram", "box", "area"]

# Fetch once at startup — runs when the module is first imported (server start),
# so every subsequent query uses the cached string with zero DB latency.
print("[Agent] Loading database schema ...")
SCHEMA = get_schema()
print("[Agent] Schema ready.")

# ── Database config ────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", "3306")),
    "user":     os.getenv("DB_USER",     "root"),
    "password": os.getenv("DB_PASSWORD", "1234"),
    "database": os.getenv("DB_NAME",     "northwind"),
}


# ── Agent state ────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages:       Annotated[list[AnyMessage], add_messages]
    question:       str
    sql_query:      str
    sql_result:     str
    dataframe_json: str
    row_count:      int
    chart_json:     str
    chart_type:     str
    chart_options:  list
    chart_reason:   str
    interpretation: str
    error:          str


# ── LLM ───────────────────────────────────────────────────────────────────────
def get_llm(model: str | None = None) -> OllamaLLM:
    model    = model or os.getenv("OLLAMA_MODEL", "llama3.2")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    return OllamaLLM(model=model, base_url=base_url, temperature=0)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _strip_code_fences(text: str, lang: str = "") -> str:
    text = re.sub(rf"```{lang}\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return text.strip()


def _get_engine():
    cfg = DB_CONFIG
    url = (
        f"mysql+mysqlconnector://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    )
    return create_engine(url, pool_pre_ping=True)


@traceable(name="execute_sql", run_type="tool")
def _run_sql(query: str) -> tuple[pd.DataFrame | None, str]:
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        engine.dispose()
        return df, ""
    except Exception as exc:
        return None, f"SQL error: {exc}"


# ── Schema-question guard ─────────────────────────────────────────────────────

_SCHEMA_KEYWORDS = {
    "what tables", "which tables", "list tables", "show tables", "all tables",
    "what columns", "which columns", "list columns", "show columns",
    "describe the database", "describe the schema", "database schema",
    "database structure", "table structure", "schema of",
    "tell me about the database", "what is in the database",
    "explain the database", "explain the schema",
    "show the schema", "show schema",
}

def _is_schema_question(question: str) -> bool:
    q = question.lower().strip()
    return any(kw in q for kw in _SCHEMA_KEYWORDS)


# ── Visualization helpers ─────────────────────────────────────────────────────

def _should_visualize(question: str, row_count: int, df: pd.DataFrame, llm: OllamaLLM) -> bool:
    if row_count < 2:
        return False
    if not df.select_dtypes(include="number").columns.tolist():
        return False

    prompt = f"""Should this SQL result be shown as a chart?

Question: {question}
Rows: {row_count}
Columns: {list(df.columns)}
Numeric columns: {df.select_dtypes(include='number').columns.tolist()}

Chart adds value for: trends, comparisons, rankings, distributions, aggregated totals across categories.
Chart does NOT add value for: single lookups, contact details, boolean answers, listing names or IDs only.

Reply with exactly YES or NO:"""
    return llm.invoke(prompt).strip().upper().startswith("Y")


def _recommend_chart(df: pd.DataFrame, question: str, llm: OllamaLLM) -> dict:
    numeric = df.select_dtypes(include="number").columns.tolist()
    text_   = df.select_dtypes(exclude="number").columns.tolist()

    prompt = f"""You are a data visualization expert. Choose the best chart type.

Question: {question}
Columns: {list(df.columns)}
Numeric columns: {numeric}
Text/categorical columns: {text_}
Row count: {len(df)}
Available types: {', '.join(CHART_TYPES)}

Reply in EXACTLY this format, nothing else:
RECOMMENDED: <one type>
OPTIONS: <2-4 types, comma-separated>
REASON: <one sentence>
"""
    response    = llm.invoke(prompt).strip()
    recommended = "bar"
    options     = ["bar", "line"]
    reason      = ""

    for line in response.splitlines():
        upper = line.upper().strip()
        if upper.startswith("RECOMMENDED:"):
            val = line.split(":", 1)[1].strip().lower()
            if val in CHART_TYPES:
                recommended = val
        elif upper.startswith("OPTIONS:"):
            vals    = [v.strip().lower() for v in line.split(":", 1)[1].split(",")]
            options = [v for v in vals if v in CHART_TYPES] or [recommended]
        elif upper.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()

    if recommended not in options:
        options = [recommended] + options

    return {"recommended": recommended, "options": options[:5], "reason": reason}


def build_plotly_chart(df: pd.DataFrame, question: str, chart_type: str) -> str:
    import plotly.express as px

    numeric = df.select_dtypes(include="number").columns.tolist()
    text_   = df.select_dtypes(exclude="number").columns.tolist()
    cols    = list(df.columns)

    _LAYOUT = dict(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(13,17,23,0.6)",
        font=dict(color="#e6edf3", size=12),
        margin=dict(l=40, r=20, t=50, b=40),
    )

    try:
        if chart_type == "pie":
            names  = text_[0]   if text_   else cols[0]
            values = numeric[0] if numeric else (cols[1] if len(cols) > 1 else cols[0])
            fig = px.pie(df.head(30), names=names, values=values, title=question)
        elif chart_type == "scatter":
            x = numeric[0] if len(numeric) >= 1 else cols[0]
            y = numeric[1] if len(numeric) >= 2 else (numeric[0] if numeric else cols[0])
            fig = px.scatter(df.head(200), x=x, y=y,
                             hover_name=text_[0] if text_ else None, title=question)
        elif chart_type == "histogram":
            x = numeric[0] if numeric else cols[0]
            fig = px.histogram(df.head(500), x=x, title=question)
        elif chart_type == "box":
            y = numeric[0] if numeric else cols[0]
            x = text_[0]   if text_   else None
            fig = px.box(df.head(200), x=x, y=y, title=question)
        elif chart_type == "area":
            x = text_[0]   if text_   else cols[0]
            y = numeric[0] if numeric else (cols[1] if len(cols) > 1 else cols[0])
            fig = px.area(df.head(100), x=x, y=y, title=question)
        elif chart_type == "line":
            x = text_[0]   if text_   else cols[0]
            y = numeric[0] if numeric else (cols[1] if len(cols) > 1 else cols[0])
            fig = px.line(df.head(100), x=x, y=y, markers=True, title=question)
        else:  # bar
            x = text_[0]   if text_   else cols[0]
            y = numeric[0] if numeric else (cols[1] if len(cols) > 1 else cols[0])
            fig = px.bar(df.head(50), x=x, y=y, title=question)

        fig.update_layout(**_LAYOUT)
        return fig.to_json()
    except Exception as exc:
        print(f"  [chart] {chart_type} build failed: {exc}", file=sys.stderr)
        return ""


# ── The single agent node ─────────────────────────────────────────────────────

def sql_analyst_node(state: AgentState) -> dict:
    llm = get_llm()

    question = state.get("question") or ""
    if not question and state.get("messages"):
        question = state["messages"][-1].content

    # ── Guard: refuse schema/structure questions ───────────────────────────
    if _is_schema_question(question):
        msg = "I can answer questions about your data, but I cannot describe or expose the database structure."
        print("\n[Guard] Schema question — refusing.")
        return {
            "question": question,
            "error":    msg,
            "messages": [AIMessage(content=msg)],
        }

    # ── SQL generation + execution (with internal retry loop) ──────────────
    sql_query  = ""
    last_error = ""
    df         = None

    for attempt in range(MAX_RETRIES + 1):
        if attempt == 0:
            print("\n[1] Generating SQL ...")
            prompt = sql_system_prompt(SCHEMA, question)
        else:
            print(f"\n[1] Retry {attempt}/{MAX_RETRIES} — correcting error ...")
            prompt = sql_retry_prompt(SCHEMA, question, sql_query, last_error)

        sql_query = _strip_code_fences(llm.invoke(prompt), "sql")
        print(f"    SQL: {sql_query[:120]}{'...' if len(sql_query) > 120 else ''}")

        check = check_sql_query(sql_query)
        if not check["allowed"]:
            last_error = check["message"]
            print(f"    Blocked by guard rails: {last_error}")
            continue

        print("\n[2] Executing ...")
        df, error = _run_sql(sql_query)
        if not error:
            break
        last_error = error
        print(f"    Error: {error}", file=sys.stderr)
    else:
        msg = f"Could not produce a valid query after {MAX_RETRIES} attempts. Last error: {last_error}"
        return {
            "question":  question,
            "sql_query": sql_query,
            "error":     last_error,
            "messages":  [AIMessage(content=msg)],
        }

    row_count  = len(df)
    sql_result = df.to_string(index=False) if not df.empty else "(no rows returned)"
    df_json    = df.to_json(orient="records", date_format="iso") if not df.empty else "[]"
    print(f"    OK — {row_count} row(s), {len(df.columns)} col(s).")

    # ── Decide visualization ───────────────────────────────────────────────
    chart_json, chart_type, chart_options, chart_reason = "", "", [], ""

    print("\n[3] Deciding visualization ...")
    if _should_visualize(question, row_count, df, llm):
        rec = _recommend_chart(df, question, llm)
        print(f"    Recommended: {rec['recommended']} — {rec['reason']}")
        chart_json    = build_plotly_chart(df, question, rec["recommended"])
        chart_type    = rec["recommended"]
        chart_options = rec["options"]
        chart_reason  = rec["reason"]
    else:
        print("    No chart needed.")

    # ── Interpret ──────────────────────────────────────────────────────────
    print("\n[4] Interpreting results ...")
    interpretation = llm.invoke(f"""You are a senior business intelligence analyst.
Analyze the SQL query results and provide a concise, actionable interpretation.

Original question: {question}
SQL query used:
{sql_query}

Results ({row_count} rows):
{sql_result[:3000]}

Provide:
1. A direct, one-sentence answer to the question.
2. Two or three key insights or patterns from the data.
3. One business recommendation if relevant.
Keep the total response under 150 words.
""").strip()

    return {
        "question":       question,
        "sql_query":      sql_query,
        "sql_result":     sql_result,
        "dataframe_json": df_json,
        "row_count":      row_count,
        "chart_json":     chart_json,
        "chart_type":     chart_type,
        "chart_options":  chart_options,
        "chart_reason":   chart_reason,
        "interpretation": interpretation,
        "error":          "",
        "messages":       [AIMessage(content=interpretation)],
    }


# ── Graph ─────────────────────────────────────────────────────────────────────
def build_agent():
    g = StateGraph(AgentState)
    g.add_node("sql_analyst", sql_analyst_node)
    g.add_edge(START, "sql_analyst")
    g.add_edge("sql_analyst", END)
    return g.compile()


# ── Public API ────────────────────────────────────────────────────────────────
def run(question: str) -> AgentState:
    agent = build_agent()
    return agent.invoke({
        "messages":       [],
        "question":       question,
        "sql_query":      "",
        "sql_result":     "",
        "dataframe_json": "[]",
        "row_count":      0,
        "chart_json":     "",
        "chart_type":     "",
        "chart_options":  [],
        "chart_reason":   "",
        "interpretation": "",
        "error":          "",
    })


# ── CLI ───────────────────────────────────────────────────────────────────────
def _print_result(result: AgentState) -> None:
    sep = "-" * 72
    print(f"\n{sep}\nQUESTION\n  {result['question']}")
    print(f"\n{sep}\nGENERATED SQL\n  {result['sql_query']}")

    if result["error"]:
        print(f"\n{sep}\nERROR\n  {result['error']}")
        return

    print(f"\n{sep}\nRESULTS  ({result['row_count']} rows)")
    lines   = result["sql_result"].splitlines()
    preview = "\n".join(lines[:21])
    if len(lines) > 21:
        preview += f"\n  ... ({len(lines) - 21} more rows)"
    print(preview)

    if result["chart_type"]:
        print(f"\n{sep}\nCHART  {result['chart_type']} — {result['chart_reason']}")

    print(f"\n{sep}\nINTERPRETATION\n{result['interpretation']}\n{sep}")


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]).strip() or "tell me the most orders by count top 10"
    _print_result(run(question))
