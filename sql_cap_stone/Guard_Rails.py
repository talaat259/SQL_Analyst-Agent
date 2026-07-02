import re

def check_sql_query(sql_query):
    """
    Scans a SQL query for keywords associated with write/destructive operations
    (e.g. INSERT, UPDATE, DELETE, DROP, etc.).

    Args:
        sql_query (str): The SQL query string to inspect.

    Returns:
        dict: {
            "allowed": bool,          # False if any write keyword was found
            "matched_keywords": list, # which keywords triggered it
            "message": str            # human-readable result
        }
    """
    write_keywords = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "TRUNCATE",
        "ALTER",
        "CREATE",
        "REPLACE",
        "MERGE",
        "GRANT",
        "REVOKE",
        "RENAME",
        "EXEC",
        "EXECUTE",
        "CALL",
    ]

    pattern = r"\b(" + "|".join(write_keywords) + r")\b"
    matches = re.findall(pattern, sql_query, re.IGNORECASE)

    # Deduplicate while preserving order, normalize to uppercase
    seen = []
    for m in matches:
        upper = m.upper()
        if upper not in seen:
            seen.append(upper)

    if seen:
        return {
            "allowed": False,
            "matched_keywords": seen,
            "message": f"Not allowed to write to the database. Triggered by: {', '.join(seen)}"
        }
    else:
        return {
            "allowed": True,
            "matched_keywords": [],
            "message": "Query allowed (read-only)."
        }


# Example usage
if __name__ == "__main__":
    queries = [
        "SELECT * FROM users WHERE id = 1",
        "DROP TABLE users; DELETE FROM logs WHERE date < '2020-01-01';",
        "UPDATE accounts SET balance = balance - 100 WHERE id = 42",
    ]

    for q in queries:
        result = check_sql_query(q)
        print(q)
        print(result)
        print()