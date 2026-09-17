import os
import time

from openai import OpenAI
from sqlalchemy import create_engine

import Schema_expert as se
from nm4_answer import generate_answer as _generate_answer
from nm4_chart import generate_chart as _generate_chart
from nm4_data import normalize_dataframe_for_display, run_query as _run_query
from nm4_schema import SchemaService
from nm4_sql import SQLService, sanitize_sql_text as _sanitize_sql_text_impl


def _load_dotenv(path: str) -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set. Add it to .env or the environment.")

client = OpenAI(api_key=OPENAI_API_KEY)


if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set. Add it to .env or the environment.")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_timeout=30,
)
SCHEMA_SQL_PATH = os.path.join(os.path.dirname(__file__), "script.sql")


# ==============================
# 🔹 SHARED SERVICES
# ==============================

def _call_openai_with_retry(**kwargs):
    last_error = None
    for attempt in range(3):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise last_error


_schema_service = SchemaService(
    schema_sql_path=SCHEMA_SQL_PATH,
    schema_profile_getter=lambda: getattr(se, "SCHEMA_PROFILE", None),
)

_sql_service = SQLService(
    call_openai_with_retry=_call_openai_with_retry,
    schema_service=_schema_service,
    schema_profile_getter=lambda: getattr(se, "SCHEMA_PROFILE", None),
)


# ==============================
# 🔹 PUBLIC API (unchanged names)
# ==============================

def get_schema():
    return _schema_service.get_schema()


def get_cached_schema() -> str:
    return _schema_service.get_cached_schema()


def _detect_question_language(question: str) -> str:
    return _sql_service.detect_question_language(question)


def _sanitize_sql_text(sql: str) -> str:
    return _sanitize_sql_text_impl(sql)


def generate_sql(question, schema=None, conversation_history=None):
    return _sql_service.generate_sql(question, schema=schema, conversation_history=conversation_history)


def run_query(sql):
    return _run_query(sql, engine=engine, sanitize_sql_text=_sanitize_sql_text)


def generate_chart(question, df):
    return _generate_chart(
        question,
        df,
        call_openai_with_retry=_call_openai_with_retry,
        normalize_dataframe_for_display=normalize_dataframe_for_display,
    )


def generate_answer(question, df, conversation_history=None):
    return _generate_answer(
        question,
        df,
        call_openai_with_retry=_call_openai_with_retry,
        detect_question_language=_detect_question_language,
        conversation_history=conversation_history,
    )


# ==============================
# 🔹 MAIN PIPELINE
# ==============================

def main():
    question = "What is the most expensive shirt and of which brand?"

    print("\n🔎 Getting schema...")
    schema = get_schema()

    print("\n🧠 Generating SQL...")
    sql = generate_sql(question, schema, conversation_history=None)
    print("\nGenerated SQL:\n", sql)

    print("\n📊 Running query...")
    df = run_query(sql)
    print("\nQuery result:\n", df)

    print("\n💡 Generating final answer...")
    answer = generate_answer(question, df, conversation_history=None)

    print("\n✅ FINAL ANSWER:\n")
    print(answer)


if __name__ == "__main__":
    main()
