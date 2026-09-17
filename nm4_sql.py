import re


class SQLService:
    def __init__(self, call_openai_with_retry, schema_service, schema_profile_getter):
        self.call_openai_with_retry = call_openai_with_retry
        self.schema_service = schema_service
        self.schema_profile_getter = schema_profile_getter

    def detect_question_language(self, question: str) -> str:
        if re.search(r"[\u0600-\u06FF]", question):
            return "arabic"
        return "english"

    def _build_schema_context_for_question(self, question: str, max_tables: int = 20) -> str:
        schema_profile = self.schema_profile_getter()
        if not schema_profile:
            return ""

        tokens = set(re.findall(r"[a-zA-Z_]+", question.lower()))
        scored = []

        for table, meta in schema_profile.items():
            table_tokens = set(re.split(r"[._]", table.lower()))
            score = 0

            if tokens & table_tokens:
                score += 3

            for col in meta.get("columns", {}).keys():
                col_tokens = set(re.split(r"[_]", col.lower()))
                if tokens & col_tokens:
                    score += 1

            if score > 0:
                scored.append((score, table))

        if not scored:
            return ""

        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = [table for _, table in scored[:max_tables]]

        parts = ["=== DATA DICTIONARY (FILTERED) ==="]
        for table in selected:
            meta = schema_profile.get(table, {})
            parts.append(f"Table: {table}")
            parts.append(f"Description: {meta.get('description')}")
            for col, cmeta in meta.get("columns", {}).items():
                dtype = cmeta.get("data_type")
                nullable = "NULL" if cmeta.get("nullable") else "NOT NULL"
                parts.append(f"  - {col} ({dtype}, {nullable})")
            parts.append("")

        return "\n".join(parts)

    def _normalize_identifier(self, identifier: str) -> str:
        cleaned = identifier.strip()
        cleaned = cleaned.replace("[", "").replace("]", "")
        if "." in cleaned:
            cleaned = cleaned.split(".")[-1]
        return cleaned.lower()

    def _extract_table_names_from_sql(self, sql: str) -> set:
        tables = set()
        pattern = re.compile(r"\bFROM\s+([^\s,;]+)|\bJOIN\s+([^\s,;]+)", re.IGNORECASE)
        for match in pattern.finditer(sql):
            token = match.group(1) or match.group(2)
            if not token:
                continue
            if token.startswith("("):
                continue
            if token.lower().startswith("select"):
                continue
            tables.add(self._normalize_identifier(token))
        return tables

    def _extract_cte_names(self, sql: str) -> set:
        ctes = set()
        for match in re.finditer(r"(?:\bwith\b|,)\s*([A-Za-z_][\w]*)\s+as\s*\(", sql, re.IGNORECASE):
            ctes.add(match.group(1).lower())
        return ctes

    def _assert_sql_uses_known_tables(self, sql: str) -> None:
        schema_index = self.schema_service.schema_index
        if schema_index is None:
            return

        known_tables = set(schema_index.keys())
        used_tables = self._extract_table_names_from_sql(sql)
        cte_names = self._extract_cte_names(sql)
        unknown_tables = sorted(t for t in used_tables if t not in known_tables and t not in cte_names)

        if unknown_tables:
            unknown_list = ", ".join(unknown_tables)
            raise ValueError(
                f"SQL references unknown tables: {unknown_list}. Please rephrase or specify the table names explicitly."
            )

    def _validate_column_table_pairs(self, sql: str) -> None:
        schema_profile = self.schema_profile_getter()
        if not schema_profile:
            return

        alias_map = {}

        from_pattern = re.compile(
            r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
            re.IGNORECASE,
        )
        for match in from_pattern.finditer(sql):
            schema_part = (match.group(1) or "dbo.").rstrip(".")
            table_name = match.group(2)
            alias = match.group(3)
            full_table = (schema_part + "." + table_name).lower()
            alias_map[alias.lower()] = full_table

        join_pattern = re.compile(
            r"\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
            re.IGNORECASE,
        )
        for match in join_pattern.finditer(sql):
            schema_part = (match.group(1) or "dbo.").rstrip(".")
            table_name = match.group(2)
            alias = match.group(3)
            full_table = (schema_part + "." + table_name).lower()
            alias_map[alias.lower()] = full_table

        column_pattern = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\b")

        for match in column_pattern.finditer(sql):
            table_ref = match.group(1).lower()
            column_name = match.group(2).lower()

            if table_ref == "dbo" or table_ref == "sys":
                continue

            actual_table = alias_map.get(table_ref)
            if not actual_table:
                for schema_table in schema_profile.keys():
                    if schema_table.lower().endswith("." + table_ref):
                        actual_table = schema_table
                        break

            if actual_table:
                if actual_table not in schema_profile:
                    for schema_table in schema_profile.keys():
                        if schema_table.lower() == actual_table:
                            actual_table = schema_table
                            break

                table_meta = schema_profile.get(actual_table, {})
                table_columns = set(c.lower() for c in table_meta.get("columns", {}).keys())

                if column_name not in table_columns:
                    if "sales" in actual_table.lower() and column_name == "received":
                        raise ValueError(
                            f"Invalid column: {match.group(1)}.{match.group(2)}\n"
                            f"ERROR: Column 'Received' does NOT exist in Sales table.\n"
                            f"'Received' exists ONLY in SalePayments table.\n"
                            f"Use: SalePayments.Received (and join Sales to SalePayments)"
                        )
                    if "sales" in actual_table.lower() and column_name == "paymenttype":
                        raise ValueError(
                            f"Invalid column: {match.group(1)}.{match.group(2)}\n"
                            f"ERROR: Column 'PaymentType' does NOT exist in Sales table.\n"
                            f"'PaymentType' exists ONLY in SalePayments table.\n"
                            f"Use: SalePayments.PaymentType (and join Sales to SalePayments)"
                        )
                    if "salepayments" in actual_table.lower() and column_name == "saleinvoiceid":
                        raise ValueError(
                            f"Invalid column: {match.group(1)}.{match.group(2)}\n"
                            f"ERROR: Column 'SaleInvoiceId' does NOT exist in SalePayments table.\n"
                            f"The correct foreign key column is 'SaleId' (not SaleInvoiceId).\n"
                            f"Use: SalePayments.SaleId to reference the Sales table."
                        )

                    available_cols = sorted([c for c in table_columns if not c.startswith("_")])[:10]
                    raise ValueError(
                        f"Invalid column: {match.group(1)}.{match.group(2)} does not exist in {actual_table}\n"
                        f"Available columns: {', '.join(available_cols)}"
                    )

    def _extract_aliases_for_table(self, sql: str, table_name: str) -> set[str]:
        aliases = set()
        pattern = re.compile(
            r"\b(?:FROM|JOIN)\s+(?:[a-zA-Z_][a-zA-Z0-9_]*\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
            re.IGNORECASE,
        )
        for match in pattern.finditer(sql):
            tbl = match.group(1).lower()
            alias = match.group(2)
            if tbl == table_name.lower():
                aliases.add(alias)
        return aliases

    def _build_alias_map(self, sql: str) -> dict[str, str]:
        alias_map = {}
        table_alias_pattern = re.compile(
            r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
            re.IGNORECASE,
        )

        for match in table_alias_pattern.finditer(sql):
            schema_part = (match.group(1) or "dbo.").rstrip(".")
            table_name = match.group(2)
            alias = match.group(3)
            alias_map[alias.lower()] = (schema_part + "." + table_name).lower()

        return alias_map

    def _normalize_data_type(self, data_type: str | None) -> str:
        if not data_type:
            return ""
        cleaned = data_type.strip().lower()
        cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()
        return cleaned

    def _build_column_type_index(self, schema_profile: dict) -> dict[tuple[str, str], str]:
        type_index = {}
        for table, meta in schema_profile.items():
            table_key = table.lower()
            for column_name, column_meta in meta.get("columns", {}).items():
                dtype = self._normalize_data_type(column_meta.get("data_type"))
                type_index[(table_key, column_name.lower())] = dtype
        return type_index

    def _fix_known_incompatible_joins(self, sql: str) -> str:
        saleitems_aliases = set(
            m.group(1)
            for m in re.finditer(
                r"\b(?:FROM|JOIN)\s+(?:\[?dbo\]?\s*\.\s*)?\[?SaleItems\]?\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
                sql,
                re.IGNORECASE,
            )
        )
        products_aliases = set(
            m.group(1)
            for m in re.finditer(
                r"\b(?:FROM|JOIN)\s+(?:\[?dbo\]?\s*\.\s*)?\[?Products\]?\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
                sql,
                re.IGNORECASE,
            )
        )

        for saleitems_alias in saleitems_aliases:
            for products_alias in products_aliases:
                sql = re.sub(
                    rf"\b{re.escape(saleitems_alias)}\.ProductId\s*=\s*{re.escape(products_alias)}\.(?:code|englishname|arabicname)\b",
                    f"{saleitems_alias}.ProductId = {products_alias}.Id",
                    sql,
                    flags=re.IGNORECASE,
                )
                sql = re.sub(
                    rf"\b{re.escape(products_alias)}\.(?:code|englishname|arabicname)\s*=\s*{re.escape(saleitems_alias)}\.ProductId\b",
                    f"{products_alias}.Id = {saleitems_alias}.ProductId",
                    sql,
                    flags=re.IGNORECASE,
                )

        sql = re.sub(
            r"\bSaleItems\.ProductId\s*=\s*Products\.(?:code|englishname|arabicname)\b",
            "SaleItems.ProductId = Products.Id",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"\bProducts\.(?:code|englishname|arabicname)\s*=\s*SaleItems\.ProductId\b",
            "Products.Id = SaleItems.ProductId",
            sql,
            flags=re.IGNORECASE,
        )

        alias_map = self._build_alias_map(sql)

        join_eq_pattern = re.compile(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b"
        )

        def _rewrite(match: re.Match) -> str:
            left_alias = match.group(1)
            left_col = match.group(2)
            right_alias = match.group(3)
            right_col = match.group(4)

            left_table = alias_map.get(left_alias.lower(), "")
            right_table = alias_map.get(right_alias.lower(), "")

            left_table_name = left_table.split(".")[-1]
            right_table_name = right_table.split(".")[-1]

            left_col_lower = left_col.lower()
            right_col_lower = right_col.lower()

            is_saleitems_products = (
                {left_table_name, right_table_name} == {"saleitems", "products"}
            )

            if is_saleitems_products:
                if left_table_name == "products" and left_col_lower in {"code", "englishname", "arabicname"} and right_col_lower == "productid":
                    return f"{left_alias}.Id = {right_alias}.{right_col}"
                if right_table_name == "products" and right_col_lower in {"code", "englishname", "arabicname"} and left_col_lower == "productid":
                    return f"{left_alias}.{left_col} = {right_alias}.Id"

            return match.group(0)

        return join_eq_pattern.sub(_rewrite, sql)

    def _validate_join_key_compatibility(self, sql: str) -> None:
        schema_profile = self.schema_profile_getter()
        if not schema_profile:
            return

        alias_map = self._build_alias_map(sql)
        if not alias_map:
            return

        type_index = self._build_column_type_index(schema_profile)
        if not type_index:
            return

        join_eq_pattern = re.compile(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b"
        )

        string_types = {"varchar", "nvarchar", "char", "nchar", "text", "ntext"}

        for match in join_eq_pattern.finditer(sql):
            left_alias = match.group(1).lower()
            left_col = match.group(2).lower()
            right_alias = match.group(3).lower()
            right_col = match.group(4).lower()

            left_table = alias_map.get(left_alias)
            right_table = alias_map.get(right_alias)
            if not left_table or not right_table:
                continue

            left_dtype = type_index.get((left_table, left_col), "")
            right_dtype = type_index.get((right_table, right_col), "")
            if not left_dtype or not right_dtype:
                continue

            mismatch = (
                (left_dtype == "uniqueidentifier" and right_dtype in string_types)
                or (right_dtype == "uniqueidentifier" and left_dtype in string_types)
            )

            if mismatch:
                left_expr = f"{match.group(1)}.{match.group(2)}"
                right_expr = f"{match.group(3)}.{match.group(4)}"
                raise ValueError(
                    "Incompatible JOIN key types detected: "
                    f"{left_expr} ({left_dtype}) = {right_expr} ({right_dtype}). "
                    "Use matching key columns (for products join via Products.Id)."
                )

    def _wrap_sum_with_coalesce(self, sql: str) -> str:
        result = []
        i = 0
        n = len(sql)

        while i < n:
            if sql[i:i + 4].lower() == "sum(":
                start = i
                j = i + 4
                depth = 1
                while j < n and depth > 0:
                    ch = sql[j]
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                    j += 1

                if depth != 0:
                    result.append(sql[i:])
                    break

                sum_expr = sql[start:j]
                prev = "".join(result).rstrip().lower()
                if prev.endswith("coalesce("):
                    result.append(sum_expr)
                else:
                    result.append(f"COALESCE({sum_expr}, 0)")

                i = j
                continue

            result.append(sql[i])
            i += 1

        return "".join(result)

    def _apply_post_generation_fixes(self, sql: str, question: str) -> str:
        sql = self._fix_known_incompatible_joins(sql)

        sql = re.sub(r"\bSalePayments\s*\.\s*SaleInvoiceId\b", "SalePayments.SaleId", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bSaleId\s*\.\s*SaleInvoiceId\b", "SalePayments.SaleId", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bsp\s*\.\s*SaleInvoiceId\b", "sp.SaleId", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bs\s*\.\s*SaleInvoiceId\b", "sp.SaleId", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bsp\s*\.\s*ChequeNumber\b", "sp.Description", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bsp\s*\.\s*Narration\b", "sp.Description", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bsp\s*\.\s*Number\b", "sp.Id", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bsp\s*\.\s*Date\b", "s.Date", sql, flags=re.IGNORECASE)

        if re.search(r"\bSales\s*\.\s*Received\b", sql, re.IGNORECASE):
            sql = re.sub(r"\bSales\s*\.\s*Received\b", "SalePayments.Received", sql, flags=re.IGNORECASE)
        if re.search(r"\bSales\s*\.\s*PaymentType\b", sql, re.IGNORECASE):
            sql = re.sub(r"\bSales\s*\.\s*PaymentType\b", "SalePayments.PaymentType", sql, flags=re.IGNORECASE)

        if re.search(r"\bPaymentMethod\b", sql, re.IGNORECASE) and re.search(r"\bSalePayments\b", sql, re.IGNORECASE):
            sql = re.sub(r"\bPaymentMethod\b", "PaymentType", sql, flags=re.IGNORECASE)
        if re.search(r"\bVoucherNumber\b", sql, re.IGNORECASE) and re.search(r"\bSales\b", sql, re.IGNORECASE):
            sql = re.sub(r"\bVoucherNumber\b", "RegistrationNo", sql, flags=re.IGNORECASE)

        payment_aliases = self._extract_aliases_for_table(sql, "SalePayments")
        for alias in payment_aliases:
            sql = re.sub(rf"\b{re.escape(alias)}\.Amount\b", f"{alias}.Received", sql)
            sql = re.sub(rf"\b{re.escape(alias)}\.TotalAmount\b", f"({alias}.Received + {alias}.DueAmount)", sql)

        sql = re.sub(r"\bSalePayments\.Amount\b", "SalePayments.Received", sql)
        sql = re.sub(r"\bSalePayments\.TotalAmount\b", "(SalePayments.Received + SalePayments.DueAmount)", sql)

        if re.search(r"\bFROM\s+dbo\.Sales\s+s\b", sql, re.IGNORECASE) and re.search(r"\bJOIN\s+dbo\.SalePayments\s+sp\b", sql, re.IGNORECASE):
            sql = re.sub(r"\bs\.Received\b", "sp.Received", sql, flags=re.IGNORECASE)
            sql = re.sub(r"\bs\.PaymentType\b", "sp.PaymentType", sql, flags=re.IGNORECASE)

        if re.search(r"\brevenue\b|\btotal\b|\bsales\b|\bamount\b|\bبيع\b|\bايراد\b", question, re.IGNORECASE):
            sql = self._wrap_sum_with_coalesce(sql)

        return sql

    def generate_sql(self, question, schema=None, conversation_history=None):
        if not schema:
            schema = self.schema_service.get_cached_schema()

        language_hint = self.detect_question_language(question)
        schema_context = self._build_schema_context_for_question(question)

        context_section = ""
        if conversation_history and len(conversation_history) > 0:
            context_section = "\n=== CONVERSATION CONTEXT ===\n"
            context_section += "Previous conversation (use this to resolve references like 'that customer', 'same period', 'those items', etc.):\n\n"
            recent_history = conversation_history[-8:] if len(conversation_history) > 8 else conversation_history
            for i, msg in enumerate(recent_history, 1):
                role_label = "User" if msg["role"] == "user" else "Assistant"
                context_section += f"[{i}] {role_label}: {msg['content'][:400]}\n"
            context_section += "\n=== CURRENT QUESTION ===\n"

        prompt = f"""
You are an expert SQL analyst specializing in financial databases. Your task is to generate precise SQL queries based on user questions.

Database schema:
{schema}
{schema_context}
{context_section}
CRITICAL INSTRUCTIONS:

1. QUERY UNDERSTANDING:
   - Read the question carefully and identify the exact data being requested
   - If this is a follow-up question, use the conversation context to understand what the user is referring to
   - Look for time periods (year, month, date range), aggregations (sum, count, average), filters (customer, product, type)
   - Identify if the user wants comparisons, rankings, or trends

2. LANGUAGE HANDLING:
   - Question language detected: {language_hint}
   - If Arabic question or Arabic names requested → use ArabicName column
   - If English question or English names requested → use EnglishName column
   - For mixed requests, use the explicitly requested language

3. SQL QUERY RULES:
   - NEVER use SELECT * - always specify exact columns needed
   - Always use table aliases (e.g., c for Customer, t for Transaction)
   - Qualify ALL columns with table aliases (e.g., c.EnglishName, not just EnglishName)
   - If same column name exists in multiple tables, alias them uniquely (e.g., t.Date as TransactionDate)
   - Use appropriate JOINs based on the relationships in the schema
   - Apply proper WHERE clauses for filtering
   - Use GROUP BY for aggregations
   - Use ORDER BY to sort results logically (e.g., by date DESC, by amount DESC)
   - Limit results when appropriate with TOP N
   - Do NOT use IsActive or IsDeleted in WHERE clauses unless the user explicitly asks

   ⚠️ CRITICAL SCHEMA RULE: ONLY USE COLUMNS THAT EXIST IN THE SCHEMA PROVIDED ABOVE
   - NEVER invent or guess column names
   - NEVER use columns with names like SaleInvoiceId, PaymentMethod, VoucherNumber, ChequeNumber, Narration - these do NOT exist
   - Every table.column reference MUST match exactly what is in the schema
   - If you cannot find the right column in the schema, ask the user to clarify
   - Double-check each column name by finding it in the schema provided
   - For payment/transaction questions: Use SalePayments table which has: Id, SaleId, Received, DueAmount, PaymentType, Amount, Description, Date (from joined Sales table)
   - Date column is in Sales table, NOT in SalePayments - use s.Date or join Sales for dates

4. COMMON PATTERNS:
   - "Total" → Use SUM() with GROUP BY
   - "Count/Number of" → Use COUNT()
   - "Top/Highest/Best" → Use ORDER BY DESC with TOP
   - "Average/Mean" → Use AVG()
   - "Between dates" → Use WHERE Date BETWEEN
   - "Year" → Use YEAR() function or compare dates

6. PAYMENTS & INVOICES - CRITICAL COLUMN MAPPING:
    - For invoice payment splits like cash/bank/credit or payment method breakdowns, use Sales + SalePayments
    - Do NOT use PaymentVouchers for sales invoice payment method questions

    ⚠️ CRITICAL: Column ownership must be strictly respected:
       - These columns exist ONLY in SalePayments, NOT in Sales:
         * dbo.SalePayments.Received (payment amount received)
         * dbo.SalePayments.DueAmount (outstanding amount)
         * dbo.SalePayments.PaymentType (payment method code)
         * dbo.SalePayments.PaymentOptionId
    - Sales table does NOT have Received or PaymentType columns
       - Sales table HAS: RegistrationNo, DocumentName, Id, InvoiceType, ReceivedAmount
        - STRICT PaymentType mapping (must be followed exactly):
            * 0 = Cash
            * 1 = Bank
            * 2 = OtherCurrency
            * 3 = CashVoucher
            * 4 = Default
            * 5 = Advance
            * 6 = Credit
        - IMPORTANT: When user asks for a payment mode/invoice type, always filter with the exact PaymentType code:
            * "cash invoice" -> SalePayments.PaymentType = 0
            * "bank invoice" -> SalePayments.PaymentType = 1
            * "other currency" -> SalePayments.PaymentType = 2
            * "cash voucher" -> SalePayments.PaymentType = 3
            * "default" -> SalePayments.PaymentType = 4
            * "advance" -> SalePayments.PaymentType = 5
            * "credit invoice" -> SalePayments.PaymentType = 6
         - NEVER reference Sales.Received - this column doesn't exist

     - For product revenue calculations, prefer dbo.SaleItems joined with dbo.Products and dbo.Sales
     - Revenue should be non-null: use COALESCE(SUM(...), 0)

    - For any payment amount, calculate PaymentAmount = SalePayments.Received (must be qualified with SalePayments table)
    - For any total amount, calculate TotalAmount = SalePayments.Received + SalePayments.DueAmount (both must be qualified)
    - Group by SalePayments.PaymentType or SalePayments.PaymentOptionId (and join lookup tables if needed)
    - There is NO column named PaymentMethod in SalePayments; use PaymentType instead
    - There is NO column named VoucherNumber in Sales; use RegistrationNo or ZatcaInvoiceNumber instead
        - In CASE labels, ALWAYS use canonical labels:
            * WHEN PaymentType = 0 THEN 'Cash'
            * WHEN PaymentType = 1 THEN 'Bank'
            * WHEN PaymentType = 2 THEN 'OtherCurrency'
            * WHEN PaymentType = 3 THEN 'CashVoucher'
            * WHEN PaymentType = 4 THEN 'Default'
            * WHEN PaymentType = 5 THEN 'Advance'
            * WHEN PaymentType = 6 THEN 'Credit'

5. FOLLOW-UP QUESTIONS:
   - "same for last year" → Modify date filters from previous query
   - "show me more" → Add more columns or remove TOP limit
   - "break down by" → Add GROUP BY clause

User Question:
{question}

Generate ONLY the SQL query. No explanations, no markdown, no code fences. Return pure T-SQL.
"""

        response = self.call_openai_with_retry(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        sql = sanitize_sql_text(response.choices[0].message.content)
        sql = self._validate_sql_against_schema(question, schema, sql)

        sql = self._apply_post_generation_fixes(sql, question)

        sql = re.sub(
            r"(\bWHEN\b\s+(?:[A-Za-z_]\w*\.)?PaymentType\s*=\s*0\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'Cash'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+0\s*=\s*(?:[A-Za-z_]\w*\.)?PaymentType\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'Cash'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+(?:[A-Za-z_]\w*\.)?PaymentType\s*=\s*1\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'Bank'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+1\s*=\s*(?:[A-Za-z_]\w*\.)?PaymentType\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'Bank'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+(?:[A-Za-z_]\w*\.)?PaymentType\s*=\s*2\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'OtherCurrency'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+2\s*=\s*(?:[A-Za-z_]\w*\.)?PaymentType\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'OtherCurrency'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+(?:[A-Za-z_]\w*\.)?PaymentType\s*=\s*3\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'CashVoucher'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+3\s*=\s*(?:[A-Za-z_]\w*\.)?PaymentType\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'CashVoucher'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+(?:[A-Za-z_]\w*\.)?PaymentType\s*=\s*4\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'Default'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+4\s*=\s*(?:[A-Za-z_]\w*\.)?PaymentType\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'Default'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+(?:[A-Za-z_]\w*\.)?PaymentType\s*=\s*5\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'Advance'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+5\s*=\s*(?:[A-Za-z_]\w*\.)?PaymentType\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'Advance'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+(?:[A-Za-z_]\w*\.)?PaymentType\s*=\s*6\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'Credit'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"(\bWHEN\b\s+6\s*=\s*(?:[A-Za-z_]\w*\.)?PaymentType\s+\bTHEN\b\s*)N?'[^']*'",
            r"\1'Credit'",
            sql,
            flags=re.IGNORECASE,
        )

        self._assert_sql_uses_known_tables(sql)

        max_validate_attempts = 2
        for attempt in range(max_validate_attempts):
            try:
                self._validate_column_table_pairs(sql)
                self._validate_join_key_compatibility(sql)
                break
            except ValueError as validation_error:
                if attempt < max_validate_attempts - 1:
                    error_msg = str(validation_error)

                    if "Incompatible JOIN key types detected" in error_msg:
                        repaired_sql = self._fix_known_incompatible_joins(sql)
                        if repaired_sql != sql:
                            sql = repaired_sql
                            continue

                    fix_prompt = f"""
The generated SQL has a schema validation error. Please fix it:

ERROR: {error_msg}

{sql}

Review the schema carefully and fix the invalid column reference. Return ONLY the corrected SQL, no explanation.
"""
                    fix_response = self.call_openai_with_retry(
                        model="gpt-4.1-mini",
                        messages=[{"role": "user", "content": fix_prompt}],
                        temperature=0,
                    )
                    sql = sanitize_sql_text(fix_response.choices[0].message.content)
                else:
                    raise

        return sql

    def _validate_sql_against_schema(self, question: str, schema: str, sql: str) -> str:
        prompt = f"""
You are an expert SQL validator for SQL Server (T-SQL). Verify and fix SQL queries against the database schema.
Your job is to FIX invalid columns - do not just identify them, actively correct them.

=== DATABASE SCHEMA ===
{schema}

=== USER QUESTION ===
{question}

=== SQL TO VALIDATE ===
{sql}

=== CRITICAL COLUMN OWNERSHIP RULES ===
⚠️ STRICT RULES - These columns have SPECIFIC table ownership:
   - dbo.SalePayments.Received = payment amount received (EXISTS ONLY in SalePayments, NOT in Sales)
   - dbo.SalePayments.DueAmount = outstanding amount (EXISTS ONLY in SalePayments, NOT in Sales)
   - dbo.SalePayments.PaymentType = payment method code (EXISTS ONLY in SalePayments, NOT in Sales)
   - dbo.SalePayments.SaleId = reference to Sales table (NOT SaleInvoiceId - that column does NOT exist)
    - dbo.Sales table does NOT have columns: Received or PaymentType
    - If the SQL references Sales.Received or Sales.PaymentType → THESE ARE ERRORS and must be corrected
   - If the SQL references SalePayments.SaleInvoiceId → This is WRONG, change to SalePayments.SaleId
        - PaymentType semantic mapping is fixed and must be used exactly:
            * 0 = Cash
            * 1 = Bank
            * 2 = OtherCurrency
            * 3 = CashVoucher
            * 4 = Default
            * 5 = Advance
            * 6 = Credit
        - If user asks for a specific mode (e.g., credit invoice), enforce exact filter (e.g., SalePayments.PaymentType = 6)
        - If query uses CASE labels for PaymentType, enforce canonical labels for all values 0..6

=== VALIDATION TASKS ===

1. SCHEMA COMPLIANCE (CRITICAL - FIX ALL ISSUES):
   - Scan every table.column reference in the SQL
   - Verify that EVERY column name actually exists in its table according to the schema
   - If a column doesn't exist, find and use the correct column name from the schema
   - EXAMPLES OF CORRECTIONS:
     * SalePayments.SaleInvoiceId → Change to SalePayments.SaleId (SaleInvoiceId does NOT exist)
    * Sales.Received → Change to SalePayments.Received (Received NOT in Sales)
     * Any non-existent column → Find the correct column in the schema and use it
   - Check that column references use correct table aliases
   - Ensure JOIN conditions reference valid foreign key relationships

2. SYNTAX VALIDATION:
   - Confirm proper T-SQL syntax
   - Check for missing/extra parentheses, commas, quotes
   - Validate aggregate functions (SUM, COUNT, AVG) are used correctly
   - Ensure GROUP BY includes all non-aggregated SELECT columns

3. QUERY LOGIC:
   - Verify the query actually answers the user's question
   - Check that WHERE conditions make sense
   - Ensure ORDER BY uses valid columns
   - Validate date/time functions if used

4. ACTIVE CORRECTIONS (DO NOT SKIP):
   - If ANY column doesn't exist in the schema: Replace with correct column name
   - If SQL uses columns from wrong table: Correct by joining proper tables
   - If syntax errors: Fix them while preserving intent
   - If logic issues: Adjust to properly answer the question
   - Do NOT ignore invalid columns - ALWAYS fix them

5. OUTPUT REQUIREMENTS:
   - Return ONLY the corrected/validated SQL query
   - NO explanations, NO comments, NO markdown
   - Pure T-SQL that is ready to execute
   - ALL invalid column references MUST be fixed
   - If original SQL has schema errors, return corrected version
   - If all is perfect, return unchanged

Return the fully corrected SQL (fix all schema errors, do not skip any invalid columns):
"""

        response = self.call_openai_with_retry(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        validated = response.choices[0].message.content.strip()
        return sanitize_sql_text(validated)


def sanitize_sql_text(sql: str) -> str:
    if not isinstance(sql, str):
        return sql

    cleaned = sql.strip()
    cleaned = re.sub(r"^\s*```[a-zA-Z0-9_]*\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    cleaned = cleaned.replace("```sql", "").replace("```SQL", "").replace("```", "")
    return cleaned.strip()
