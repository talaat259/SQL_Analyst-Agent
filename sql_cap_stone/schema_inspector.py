"""
Dynamically inspect the connected MySQL database and return a schema string
suitable for injection into an LLM prompt.

The result is cached after the first call so the DB is only queried once
per process lifetime.
"""

import os
from functools import lru_cache

from sqlalchemy import create_engine, inspect as sa_inspect
from dotenv import load_dotenv

load_dotenv()


def _engine():
    user     = os.getenv("DB_USER",     "root")
    password = os.getenv("DB_PASSWORD", "1234")
    host     = os.getenv("DB_HOST",     "localhost")
    port     = os.getenv("DB_PORT",     "3306")
    database = os.getenv("DB_NAME",     "northwind")
    url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_schema() -> str:
    """
    Return a compact schema string describing every table in the database.

    Includes column names, SQL types, primary-key markers, and foreign-key
    references so the LLM can write correct JOINs without being told the
    relationships up front.
    """
    engine = _engine()
    insp   = sa_inspect(engine)

    db_name = engine.url.database
    lines   = [f"MySQL database: {db_name}", "", "Tables:"]

    for table in sorted(insp.get_table_names()):
        columns = insp.get_columns(table)
        pks     = set(insp.get_pk_constraint(table).get("constrained_columns", []))

        # map each column to its FK target (if any)
        fk_map: dict[str, str] = {}
        for fk in insp.get_foreign_keys(table):
            for local_col, ref_col in zip(
                fk["constrained_columns"], fk["referred_columns"]
            ):
                fk_map[local_col] = f"{fk['referred_table']}.{ref_col}"

        col_parts = []
        for col in columns:
            name = col["name"]
            typ  = str(col["type"])
            tags = []
            if name in pks:
                tags.append("PK")
            if name in fk_map:
                tags.append(f"FK->{fk_map[name]}")
            suffix = f"  [{', '.join(tags)}]" if tags else ""
            col_parts.append(f"    {name} {typ}{suffix}")

        lines.append(f"  {table}(")
        lines.extend(col_parts)
        lines.append("  )")

    engine.dispose()
    return "\n".join(lines)
