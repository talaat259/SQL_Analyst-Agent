def sql_system_prompt(schema: str, question: str) -> str:
    return f"""You are an expert MySQL analyst.
given the following schema and question reply you can return insights or generate SQL queries that
will answer the question.

Schema:
{schema}

Question: {question}

Instructions:
- Use backticks for table/column names if they contain special characters.
- Join tables when needed using the FK relationships shown in the schema.
- Limit to 100 rows unless the question requires otherwise.
"""


def sql_retry_prompt(schema: str, question: str, failed_sql: str, error: str) -> str:
    return f"""You are an expert MySQL analyst. Your previous SQL query failed.
Fix it based on the error message below.

Schema:
{schema}

Question: {question}

Your previous (broken) SQL:
{failed_sql}

Error:
{error}

Instructions:
- Return ONLY the corrected SQL query, no explanation or markdown.
- Address the specific error above.
- Use backticks for table/column names if they contain special characters.
- Limit to 100 rows unless the question requires otherwise.
"""
