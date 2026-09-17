import os
import re


class SchemaService:
    def __init__(self, schema_sql_path: str, schema_profile_getter):
        self.schema_sql_path = schema_sql_path
        self.schema_profile_getter = schema_profile_getter
        self._schema_cache = None
        self._schema_index = None

    @property
    def schema_index(self):
        return self._schema_index

    def get_schema(self):
        if self._schema_cache is not None:
            return self._schema_cache

        schema_profile = self.schema_profile_getter()
        if schema_profile:
            self._schema_cache = self._build_schema_from_profile(schema_profile)
            self._schema_index = self._build_schema_index_from_profile(schema_profile)
            return self._schema_cache

        if not os.path.exists(self.schema_sql_path):
            raise FileNotFoundError(f"Schema file not found: {self.schema_sql_path}")

        sql_text = self._read_schema_file(self.schema_sql_path)
        self._schema_index = self._build_schema_index(sql_text)
        self._schema_cache = self._parse_schema_from_sql(sql_text)
        return self._schema_cache

    def get_cached_schema(self) -> str:
        return self.get_schema()

    def _parse_schema_from_sql(self, sql_text: str) -> str:
        schema_parts = []

        table_pattern = re.compile(
            r"CREATE\s+TABLE\s+\[(?P<schema>[^\]]+)\]\.\[(?P<table>[^\]]+)\]\s*\((?P<body>.*?)\)\s*(?:ON|TEXTIMAGE_ON)",
            re.IGNORECASE | re.DOTALL,
        )

        column_pattern = re.compile(
            r"^\s*\[(?P<col>[^\]]+)\]\s+\[(?P<type>[^\]]+)\]",
            re.IGNORECASE,
        )

        for match in table_pattern.finditer(sql_text):
            table_name = match.group("table")
            body = match.group("body")

            columns = []
            for line in body.splitlines():
                if "CONSTRAINT" in line.upper():
                    continue
                col_match = column_pattern.match(line)
                if col_match:
                    col_name = col_match.group("col")
                    col_type = col_match.group("type")
                    columns.append(f"  - {table_name}.{col_name} ({col_type})")

            if columns:
                schema_parts.append(f"Table: {table_name}\n" + "\n".join(columns))

        return "\n\n".join(schema_parts)

    def _build_schema_from_profile(self, profile: dict) -> str:
        schema_parts = []
        for table, meta in profile.items():
            columns = []
            for col, cmeta in meta.get("columns", {}).items():
                col_type = cmeta.get("data_type")
                columns.append(f"  - {table}.{col} ({col_type})")
            if columns:
                schema_parts.append(f"Table: {table}\n" + "\n".join(columns))
        return "\n\n".join(schema_parts)

    def _build_schema_index_from_profile(self, profile: dict) -> dict:
        index = {}
        for table, meta in profile.items():
            table_key = table.split(".")[-1].lower()
            columns = {col.lower() for col in meta.get("columns", {}).keys()}
            index[table_key] = columns
        return index

    def _build_schema_index(self, sql_text: str) -> dict:
        index = {}

        table_pattern = re.compile(
            r"CREATE\s+TABLE\s+\[(?P<schema>[^\]]+)\]\.\[(?P<table>[^\]]+)\]\s*\((?P<body>.*?)\)\s*(?:ON|TEXTIMAGE_ON)",
            re.IGNORECASE | re.DOTALL,
        )

        column_pattern = re.compile(
            r"^\s*\[(?P<col>[^\]]+)\]\s+\[(?P<type>[^\]]+)\]",
            re.IGNORECASE,
        )

        for match in table_pattern.finditer(sql_text):
            table_name = match.group("table")
            body = match.group("body")
            columns = set()

            for line in body.splitlines():
                if "CONSTRAINT" in line.upper():
                    continue
                col_match = column_pattern.match(line)
                if col_match:
                    columns.add(col_match.group("col").lower())

            index[table_name.lower()] = columns

        return index

    def _read_schema_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as file:
                return file.read()
        except UnicodeDecodeError:
            pass

        try:
            with open(path, "r", encoding="utf-8-sig") as file:
                return file.read()
        except UnicodeDecodeError:
            pass

        try:
            with open(path, "r", encoding="utf-16") as file:
                return file.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as file:
                return file.read()
