from typing import Any, List, Dict, Optional
from langchain.tools import BaseTool
from pydantic import PrivateAttr
from sqlalchemy import text

class SQLDBListStatFuncTool(BaseTool):
    # """
    # Returns a listing of statistical DB functions whose names start with 'stat'.
    # The agent can call this tool to discover function names, signatures and example calls.
    # """
    """
    List functions in the database for use in database queries.
    The agent can call this tool to discover function names, signatures and example calls.
    """

    # private attrs (not Pydantic fields)
    _parent: Any = PrivateAttr()
    _schema: str = PrivateAttr()
    _prefix: str = PrivateAttr()
    _limit: Optional[int] = PrivateAttr()

    def __init__(self, parent, schema: str = "public", prefix: str = "stat", limit: Optional[int] = None, **kwargs):
        # initialize BaseTool
        super().__init__(name="sql_db_list_statistical_functions", 
                        description="List statistical functions defined in the database."
                        )
        self._parent = parent
        self._schema = schema
        self._prefix = (prefix or "").lower()
        self._limit = limit

    def _get_engine(self):
        return self._parent._get_engine()

    def _run(self, tool_input: Optional[str] = None) -> str:
        """
        Ignores tool_input (keeps signature), returns the stat function list.
        """
        sql = """
        SELECT
            n.nspname AS schema_name,
            p.proname AS func_name,
            pg_get_function_arguments(p.oid) AS args,
            pg_get_function_result(p.oid) AS returns,
            coalesce(d.description, '') AS comment
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        LEFT JOIN pg_description d ON d.objoid = p.oid
        WHERE n.nspname = :schema
          AND n.nspname NOT IN ('pg_catalog','information_schema')
          AND lower(p.proname) LIKE :prefix_like
        ORDER BY p.proname
        """
        if self._limit:
            sql += " LIMIT :limit"

        params = {"schema": self._schema, "prefix_like": f"{self._prefix}%"}
        if self._limit:
            params["limit"] = int(self._limit)

        eng = self._get_engine()
        with eng.connect() as conn:
            result = conn.execute(text(sql), params)
            # use Result.mappings() to get dict-like rows (works across SQLAlchemy versions)
            rows = result.mappings().all()

        if not rows:
            return "(no stat* functions found)"

        lines: List[str] = ["-- FUNCTIONS --"]
        for r in rows:
            args = r["args"] or ""
            returns = r["returns"] or ""
            comment = (r["comment"] or "").strip()
            example_args = self._example_placeholders(args)
            example_sql = f"SELECT {r['schema_name']}.{r['func_name']}({example_args});" if example_args != "" else f"SELECT {r['schema_name']}.{r['func_name']}();"
            line = f"{r['schema_name']}.{r['func_name']}({args}) -> {returns}"
            lines.append(line)
            if comment:
                lines.append(f"  description: {comment}")
            lines.append(f"  example: {example_sql}")
            lines.append("")  # blank line
        return "\n".join(lines)

    async def _arun(self, tool_input: Optional[str] = None) -> str:
        return self._run(tool_input)

    @staticmethod
    def _example_placeholders(arg_string: str) -> str:
        if not arg_string:
            return ""
        parts = [p.strip() for p in arg_string.split(",") if p.strip()]
        return ", ".join(str(i + 1) for i in range(len(parts)))
