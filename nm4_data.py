import json
import re
import time
from decimal import Decimal

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def _is_transient_db_error(exc: Exception) -> bool:
    message = str(exc).lower()
    transient_markers = [
        "communication link failure",
        "connection is busy",
        "connection was closed",
        "connection reset",
        "connection aborted",
        "transport-level error",
        "server has gone away",
        "login timeout expired",
        "timeout expired",
    ]
    return any(marker in message for marker in transient_markers)


def run_query(sql: str, engine, sanitize_sql_text):
    sql = sanitize_sql_text(sql)
    if re.search(r"\bFROM\s+dbo\.Sales\s+s\b", sql, re.IGNORECASE) and re.search(r"\bJOIN\s+dbo\.SalePayments\s+sp\b", sql, re.IGNORECASE):
        sql = re.sub(r"\bs\.Received\b", "sp.Received", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bs\.PaymentType\b", "sp.PaymentType", sql, flags=re.IGNORECASE)

    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            with engine.begin() as conn:
                result = conn.execute(text(sql))
                if not result.returns_rows:
                    return pd.DataFrame()
                return pd.DataFrame(result.fetchall(), columns=result.keys())
        except DBAPIError as exc:
            is_last_attempt = attempt >= max_attempts - 1
            should_retry = bool(getattr(exc, "connection_invalidated", False)) or _is_transient_db_error(exc)
            if is_last_attempt or not should_retry:
                raise
            engine.dispose()
            time.sleep(0.5)


def normalize_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    safe_df = df.copy()
    safe_df.columns = _dedupe_columns(safe_df.columns)

    for col in safe_df.columns:
        series = safe_df[col]
        if pd.api.types.is_object_dtype(series):
            safe_df[col] = series.map(_normalize_cell_value)
        else:
            safe_df[col] = series.map(_normalize_cell_value)

    return safe_df


def _dedupe_columns(columns) -> list:
    seen = {}
    deduped = []

    for col in columns:
        if col not in seen:
            seen[col] = 0
            deduped.append(col)
        else:
            seen[col] += 1
            deduped.append(f"{col}_{seen[col]}")

    return deduped


def _normalize_cell_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.hex()
    if isinstance(value, (dict, list, tuple, set)):
        try:
            return json.dumps(value, default=str)
        except Exception:
            return str(value)
    return value
