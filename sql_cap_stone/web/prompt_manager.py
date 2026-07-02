import json
import os
import sys
from datetime import datetime, timezone

# Parent directory on path so we can access Ollama env vars via dotenv
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from dotenv import load_dotenv
load_dotenv(os.path.join(_parent, ".env"))

DEFAULT_TEMPLATE = """\
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
"""

_HISTORY_LIMIT = 20


class PromptManager:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "system_prompt.json")
        if not os.path.exists(self.path):
            self._write(DEFAULT_TEMPLATE, [])

    def _read(self) -> dict:
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, template: str, history: list) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"template": template, "history": history}, f, indent=2)

    def get_template(self) -> str:
        return self._read()["template"]

    def get_history(self) -> list:
        return self._read().get("history", [])

    def save_template(self, new_template: str) -> None:
        data = self._read()
        history = data.get("history", [])
        history.append({
            "template": data["template"],
            "saved_at": datetime.now(timezone.utc).isoformat(),
        })
        self._write(new_template, history[-_HISTORY_LIMIT:])

    def render(self, schema: str, question: str) -> str:
        return self.get_template().replace("{SCHEMA}", schema).replace("{question}", question)

    def suggest_from_feedback(self, feedback_text: str) -> str:
        """Use the local Ollama LLM to suggest a revised system prompt."""
        from langchain_ollama import OllamaLLM

        model = os.getenv("OLLAMA_MODEL", "llama3.2")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        llm = OllamaLLM(model=model, base_url=base_url, temperature=0.3)

        current = self.get_template()
        meta_prompt = f"""You are a prompt engineer improving an AI SQL analyst's system prompt.

A user submitted this style feedback:
"{feedback_text}"

Current system prompt template (uses {{SCHEMA}} and {{question}} as literal placeholders — keep them exactly as-is):
---
{current}
---

Revise the system prompt to incorporate the feedback while keeping it concise and focused on SQL generation.
Return ONLY the revised prompt text with no preamble or explanation.
"""
        return llm.invoke(meta_prompt).strip()
