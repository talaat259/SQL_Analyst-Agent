# SQL Agent

An agentic SQL assistant that converts natural language questions into executable database queries with built-in safety constraints, adaptive prompting, and interactive visualization.

## Project Structure

```
sql_cap_stone/
├── agent.py                 # Main agent with graph logic and execution loop
├── Guard_Rails.py          # Keyword-based query safety validation
├── schema_inspector.py      # Dynamic database schema introspection
├── sql_Agent_prompt.py      # Static prompt templates (overridden by web UI)
├── langgraph.json          # LangGraph configuration
├── requirements.txt        # Python dependencies
└── web/
    ├── app.py              # FastAPI web interface
    ├── prompt_manager.py    # Dynamic system prompt management
    ├── feedback_store.py    # User feedback persistence
    └── data/
        ├── system_prompt.json   # Customizable prompt template
        └── feedback.json        # Feedback history
```

## Architecture Overview

### Single-Node Graph Pattern

The agent uses **LangGraph** to implement a single self-contained node that handles the entire query lifecycle internally:

```
START → sql_analyst_node (with internal retry loop) → END
```

The node internally orchestrates:
1. Schema validation guard
2. SQL generation (with error retry loop)
3. Query execution
4. Visualization decision
5. Charting (optional)
6. Result interpretation

This single-node design reduces complexity while maintaining a clear execution flow.

## Core Components

### 1. LLM Backend

- **Engine**: Ollama (local LLM inference)
- **Library**: langchain-ollama for integration
- **Model**: Configurable (default: llama3.2)
- **Temperature**: 0 (deterministic responses)

The agent uses local LLMs for privacy and control, avoiding external API calls.

### 2. Database Layer

- **Database**: MySQL
- **ORM**: SQLAlchemy for connection pooling and query execution
- **Driver**: mysql-connector-python
- **Schema Caching**: LRU cache with single-query-at-startup pattern

Database schema is introspected once at agent startup via `schema_inspector.py`, which extracts:
- Table names and structures
- Column names and SQL types
- Primary key constraints
- Foreign key relationships (for intelligent JOIN generation)

### 3. Query Guardrails

**Keyword-Based Blocking** (`Guard_Rails.py`):
- Scans queries for write operations: INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, CREATE, REPLACE, MERGE, GRANT, REVOKE, RENAME, EXEC, EXECUTE, CALL
- Returns: `allowed: bool`, matched keywords, human-readable message
- Applied before every query execution

**Schema Question Guard** (in `agent.py`):
- Detects questions asking to expose database structure
- Keywords: "what tables", "list columns", "show schema", "database structure", etc.
- Blocks and returns safe refusal message instead of executing query

### 4. Dynamic System Prompts

**PromptManager** (`prompt_manager.py`):
- Loads customizable prompt template from `system_prompt.json`
- Supports template variables: `{SCHEMA}` and `{question}`
- Maintains prompt version history (last 20 versions)
- Users can edit prompts via web UI without code changes

**Default Template**:
```
You are an expert MySQL analyst.
Convert the question below into a valid MySQL SELECT query.

Schema:
{SCHEMA}

Question: {question}

Instructions:
- Return ONLY the SQL query, no explanation or markdown.
- Use backticks for table/column names if they contain special characters.
- Join tables when needed.
- Limit to 100 rows unless the question requires otherwise.
```

**Retry Prompt** (for error recovery):
- Includes the failed query and error message
- Instructs LLM to fix the specific error
- Maintains schema context for correction

### 5. Query Execution & Retry Logic

**Execution Flow**:
1. Generate SQL from natural language (with LLM)
2. Check SQL against guardrails
3. If blocked, retry with error context (up to 100 retries)
4. Execute query via SQLAlchemy
5. If error, retry with error message injected into prompt
6. Continue until success or max retries exceeded

**Error Recovery**:
- Catches SQL execution exceptions
- Feeds error message back to LLM prompt
- LLM attempts to fix the query
- Prevents infinite loops with MAX_RETRIES limit

### 6. Visualization System

**Visualization Decision**:
- Checks if result has >= 2 rows
- Checks if result has numeric columns
- Asks LLM: "Should this result be visualized as a chart?"
- Decision based on question and data characteristics

**Chart Recommendation**:
- LLM recommends primary chart type
- Suggests 2-4 alternative types
- Provides reasoning

**Supported Chart Types**:
- bar (default)
- line
- scatter
- pie
- histogram
- box
- area

**Plotly Implementation**:
- Builds interactive charts with Plotly Express
- Dark theme for web UI
- Auto-selects columns: first text column for X, first numeric for Y
- Limits data points to prevent performance issues (50-500 rows depending on type)

### 7. Web Interface

**FastAPI Backend** (`web/app.py`):
- `/api/chat` - Submit questions and receive results
- `/api/chart` - Generate custom charts from results
- `/api/feedback` - Submit feedback on agent responses
- `/api/prompt/*` - View/edit/history system prompts
- `/api/suggest-prompt` - Use LLM to improve prompt based on feedback

**Request/Response Models** (Pydantic):
- ChatRequest: `message` (string)
- ChartRequest: `dataframe_json`, `question`, `sql_query`, `chart_type`
- FeedbackRequest: `message_id`, `rating`, `text`, `type`
- PromptUpdateRequest: `template`

**Response Structure**:
```json
{
  "question": "user's original question",
  "sql_query": "generated SQL",
  "sql_result": "formatted table string",
  "dataframe_json": "JSON array of records",
  "row_count": 42,
  "chart_json": "Plotly JSON spec",
  "chart_type": "bar",
  "chart_options": ["bar", "line", "area"],
  "interpretation": "natural language summary"
}
```

## Technical Stack

### Python Dependencies

```
langgraph>=0.2.0              # Agent graph orchestration
langchain-ollama>=0.1.0       # Ollama LLM integration
langchain-core>=0.2.0         # LangChain primitives
langsmith>=0.1.0              # LangChain tracing/debugging
mysql-connector-python>=8.0.0 # MySQL driver
sqlalchemy>=2.0.0             # Database ORM
plotly>=5.0.0                 # Interactive visualizations
pandas>=2.0.0                 # Data manipulation
matplotlib>=3.7.0             # Static charting
python-dotenv>=1.0.0          # Environment variables
fastapi>=0.100.0              # Web framework
uvicorn>=0.23.0               # ASGI server
pydantic>=2.0.0               # Data validation
```

### Architecture Patterns

**State Management**:
- TypedDict-based agent state (LangGraph pattern)
- Message history with `add_messages` reducer
- State mutations passed through node returns

**Traceable Functions**:
- LangSmith decorators for debugging
- SQL execution instrumented with `@traceable`
- Helpful for monitoring and troubleshooting

**Environment Configuration**:
- `.env` file with database credentials and Ollama settings
- Defaults provided for all env vars (for testing)
- Loaded via `python-dotenv`

## Execution Flow

### User Query → Result

1. **User submits question** via `/api/chat`
2. **Guard check**: Is this a schema exposure question? → Refuse if yes
3. **SQL generation**: LLM produces SELECT query from question + schema
4. **Guard check**: Does query contain write keywords? → Block if yes
5. **Execution**: Run query against MySQL database
   - If error → Feed error to LLM, retry (max 100 attempts)
   - If success → Continue to step 6
6. **Visualization decision**: Recommend chart type (if applicable)
7. **Chart generation**: Build Plotly JSON for selected type
8. **Response**: Return question, SQL, results, visualization, interpretation

### Prompt Customization Workflow

1. **Admin visits web UI** → Views current system prompt
2. **Tries chatting** → Observes agent behavior
3. **Submits feedback** via feedback form
4. **Clicks "Suggest Improvement"** → LLM generates revised prompt
5. **Reviews suggestion** → Can accept/reject/edit
6. **Saves new prompt** → Old version archived in history
7. **Next query** → Uses new prompt template

## Configuration

### Environment Variables

```bash
# Database
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=1234
DB_NAME=northwind

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Web server
PYTHONUNBUFFERED=1
```

### Running the Agent

**Standalone graph**:
```bash
cd sql_cap_stone
python -m langgraph up
```

**Web interface**:
```bash
cd sql_cap_stone/web
uvicorn app:app --reload --port 8000
```

## Safety & Constraints

### Hard Constraints

- **Read-only**: Guardrails block all write operations
- **Schema hiding**: Refuses to describe database structure
- **No code execution**: LLM-generated SQL only, no arbitrary code
- **Connection pooling**: SQLAlchemy manages DB connections safely

### Soft Constraints

- **Query limits**: Default 100 rows (modifiable in prompt)
- **Retry limits**: Max 100 retries to prevent infinite loops
- **Visualization limits**: Data sampling to prevent rendering timeouts

## Limitations

- **Single database**: Currently wired to one MySQL instance
- **Local LLM**: Requires running Ollama server locally
- **No parameterized queries**: Queries are generated as full SQL strings
- **Basic NL understanding**: Relies on LLM quality; ambiguous questions may fail
- **No query optimization**: Doesn't analyze execution plans or suggest indexes
- **Static schema**: Schema cached at startup; new tables require restart

## Future Enhancements

- Multi-database support with dynamic selection
- Query optimization suggestions
- Cached query results for repeated questions
- User-specific permission boundaries
- Semantic caching of questions/answers
- Integration with data catalogs and data lineage tools
