import json
import re

import pandas as pd
import plotly.express as px


def generate_chart(question: str, df: pd.DataFrame, call_openai_with_retry, normalize_dataframe_for_display):
    if df is None or df.empty:
        return None, "Graphical view for this query not possible (no data)."

    safe_df = normalize_dataframe_for_display(df)

    spec = _get_chart_spec(question, safe_df, call_openai_with_retry)
    if not spec:
        return None, "Graphical view for this query not possible."

    chart_type = spec.get("chart_type", "none")
    if chart_type == "none":
        fig = _try_rule_based_chart(question, safe_df)
        if fig is not None:
            return fig, None
        reason = spec.get("reason") or "Graphical view for this query not possible."
        return None, reason

    try:
        fig = _build_chart_from_spec(safe_df, spec)
    except Exception:
        return None, "Graphical view for this query not possible."

    if fig is None:
        return None, "Graphical view for this query not possible."

    return fig, None


def _get_chart_spec(question: str, df: pd.DataFrame, call_openai_with_retry) -> dict | None:
    summary = _summarize_dataframe_for_chart(df)

    prompt = f"""
You are an expert data visualization specialist. Analyze the user's question and data to recommend the best chart type.

=== USER QUESTION ===
{question}

=== DATA SUMMARY ===
{summary}

=== CHART TYPE SELECTION GUIDE ===

**BAR CHART** - Use when:
- Comparing categories or groups
- Showing rankings or top/bottom items
- Displaying counts or sums by category
- Example: Sales by customer, products by category, revenue by region

**PIE CHART** - Use when:
- Showing parts of a whole (percentages/proportions)
- Limited categories (2-8 slices work best)
- User asks about "distribution", "share", "percentage"
- Example: Market share, expense breakdown, customer segments

**LINE CHART** - Use when:
- Data has time dimension (dates, years, months)
- Showing trends over time
- Comparing multiple series over time
- Example: Sales over months, growth trends, time series data

**HISTOGRAM** - Use when:
- Showing distribution of a single numeric variable
- Understanding data spread or frequency
- Example: Age distribution, price ranges, score distribution

**SCATTER PLOT** - Use when:
- Comparing two numeric variables
- Looking for correlations or relationships
- Example: Price vs quantity, age vs spending, cost vs revenue

**NONE** - Use when:
- Data is purely tabular (names, IDs, single values)
- No meaningful visual representation
- Too few data points (1-2 rows)
- Data is text-heavy

=== YOUR TASK ===

1. Analyze the question intent (comparison? trend? distribution? composition?)
2. Examine the data structure (columns, types, row count)
3. Select the MOST appropriate chart type
4. Identify which columns to use for x, y, and optional color
5. Create a descriptive title

=== OUTPUT FORMAT ===

Return ONLY valid JSON with this exact structure:
{{
  "chart_type": "bar|pie|line|histogram|scatter|none",
  "x": "column_name_or_null",
  "y": "column_name_or_null", 
  "color": "column_name_or_null",
  "title": "Descriptive chart title",
  "reason": "Brief explanation (only if chart_type is none)"
}}

CRITICAL RULES:
- Use EXACT column names from the data summary
- Set null for unused fields (use null, not "null")
- If no good chart exists, use chart_type="none" and explain in reason
- Ensure the chart type matches the question intent
- Title should be clear and descriptive

Generate the JSON specification now:
"""

    response = call_openai_with_retry(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        spec = json.loads(raw)
    except Exception:
        return None

    if not isinstance(spec, dict):
        return None

    return spec


def _summarize_dataframe_for_chart(df: pd.DataFrame) -> str:
    dtype_map = {col: str(dtype) for col, dtype in df.dtypes.items()}
    sample_rows = df.head(5).to_dict(orient="records")

    return json.dumps(
        {
            "columns": list(df.columns),
            "dtypes": dtype_map,
            "sample_rows": sample_rows,
            "row_count": int(len(df)),
        },
        ensure_ascii=True,
        default=str,
    )


def _build_chart_from_spec(df: pd.DataFrame, spec: dict):
    chart_type = spec.get("chart_type")
    x_col = spec.get("x")
    y_col = spec.get("y")
    color_col = spec.get("color")
    title = spec.get("title") or ""

    if chart_type not in {"bar", "pie", "histogram", "line", "scatter"}:
        return None

    if x_col and x_col not in df.columns:
        return None
    if y_col and y_col not in df.columns:
        return None
    if color_col and color_col not in df.columns:
        color_col = None

    if chart_type == "histogram":
        if not x_col:
            return None
        if not _is_numeric_series(df[x_col]):
            return None
        return px.histogram(df, x=x_col, title=title)

    if chart_type == "scatter":
        if not x_col or not y_col:
            return None
        if not _is_numeric_series(df[x_col]) or not _is_numeric_series(df[y_col]):
            return None
        return px.scatter(df, x=x_col, y=y_col, color=color_col, title=title)

    if chart_type == "line":
        if not x_col or not y_col:
            return None
        return px.line(df, x=x_col, y=y_col, color=color_col, title=title)

    if chart_type == "bar":
        if not x_col:
            return None
        if y_col:
            if not _is_numeric_series(df[y_col]):
                return None
            return px.bar(df, x=x_col, y=y_col, color=color_col, title=title)
        counts = df[x_col].value_counts().reset_index()
        counts.columns = [x_col, "count"]
        return px.bar(counts, x=x_col, y="count", title=title)

    if chart_type == "pie":
        if not x_col:
            return None
        if y_col:
            if not _is_numeric_series(df[y_col]):
                return None
            return px.pie(df, names=x_col, values=y_col, title=title)
        counts = df[x_col].value_counts().reset_index()
        counts.columns = [x_col, "count"]
        return px.pie(counts, names=x_col, values="count", title=title)

    return None


def _is_numeric_series(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.notna().any()


def _try_rule_based_chart(question: str, df: pd.DataFrame):
    if not re.search(r"\byear\b|yearly|year\s*wise", question, re.IGNORECASE):
        return None

    date_col = _find_date_column(df)
    if not date_col:
        return None

    temp = df.copy()
    temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce")
    temp = temp[temp[date_col].notna()]
    if temp.empty:
        return None

    temp["__year__"] = temp[date_col].dt.year

    numeric_cols = [col for col in temp.columns if _is_numeric_series(temp[col])]
    numeric_cols = [col for col in numeric_cols if col not in {"__year__"}]

    credit_col = _find_column_case_insensitive(temp, "totalcredit")
    debit_col = _find_column_case_insensitive(temp, "totaldebit")

    if credit_col and debit_col:
        grouped = (
            temp.groupby("__year__", as_index=False)[[credit_col, debit_col]]
            .sum()
            .sort_values("__year__")
        )
        melted = grouped.melt(
            id_vars="__year__",
            value_vars=[credit_col, debit_col],
            var_name="Type",
            value_name="Amount",
        )
        return px.bar(
            melted,
            x="__year__",
            y="Amount",
            color="Type",
            barmode="group",
            title="Year-wise Total Credit vs Total Debit",
        )

    if len(numeric_cols) == 1:
        y_col = numeric_cols[0]
        grouped = temp.groupby("__year__", as_index=False)[y_col].sum()
        grouped = grouped.sort_values("__year__")
        return px.bar(grouped, x="__year__", y=y_col, title="Year-wise totals")

    counts = temp.groupby("__year__", as_index=False).size()
    counts = counts.rename(columns={"size": "count"}).sort_values("__year__")
    return px.bar(counts, x="__year__", y="count", title="Year-wise counts")


def _find_date_column(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col

    for col in df.columns:
        if re.search(r"date|time|created|updated", col, re.IGNORECASE):
            return col

    return None


def _find_column_case_insensitive(df: pd.DataFrame, target: str) -> str | None:
    for col in df.columns:
        if col.lower() == target.lower():
            return col
    return None
