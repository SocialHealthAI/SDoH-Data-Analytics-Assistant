from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from typing import Callable, List, Any
import re

class SQLTools:
    """
    SQLTools is a helper class that wraps LangChain's SQLDatabaseToolkit for use in agent workflows.
    The database is defined by LangChain SQLDatabase.from_uri(db_uri) which wraps a SQLAlchemy engine.
    The engine is created by SQLDatabase. The engine supports a local SQLLite database and external daabases.

    The SQLDatabaseToolkit auto-builds:
        - QuerySQLDatabaseTool → run arbitrary SQL queries.
        - InfoSQLDatabaseTool → get database schema information.
        - ListSQLDatabaseTool → list available tables.
    and it wires these tools to the SQLDatabase and LLM.

    Example:
        sql_tools = SQLTools(db_uri="sqlite:///example.db", llm=my_llm)
        tools = sql_tools.get_tools() + [my_other_tool]
        agent = initialize_agent(tools, my_llm, ...)
    """
    def __init__(self, db_uri: str, llm=None):
        """
        Initialize the SQLTools helper.

        Args:
            db_uri (str): The SQLite database URI, e.g., 'sqlite:///example.db'
            llm: The LLM to pass to the toolkit. Required for tools that auto-generate SQL.
        """
        # disable sample rows in the table info to avoid sending sample data into prompts
        self.db = SQLDatabase.from_uri(db_uri, sample_rows_in_table_info=0)
        self.llm = llm or ChatOpenAI()  # fallback if none provided
        self.toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
   
    def _reject_select_star_wrapper(self, original_fn: Callable) -> Callable:
        def wrapped(**kwargs):
            # Accept common key names used by different tools
            query_key = None
            if "query" in kwargs:
                query_key = "query"
            elif "sql" in kwargs:
                query_key = "sql"

            if query_key:
                q = (kwargs.get(query_key) or "").strip()
                if _SELECT_STAR_RE.search(q):
                    raise ValueError(
                        "Queries containing SELECT * or alias.* are not allowed. "
                        "Please specify explicit columns in the SELECT clause."
                    )
            return original_fn(**kwargs)

        return wrapped

    def get_tools(self):
        tools = self.toolkit.get_tools()

        for tool in tools:
            if tool.name == "sql_db_query":
                tool.description = "Run a detailed and valid SQL query against the database. DO NOT use SELECT * or alias.*; explicitly list the columns you need. "
                try:
                    tool.func = self._reject_select_star_wrapper(tool.func)
                except Exception:
                    # defensive: if we can't wrap, leave original function but keep description
                    pass

            elif tool.name == "sql_db_query_checker":
                tool.description = "Check if a given SQL query is syntactically valid before execution. This checker will reject queries containing SELECT * or alias.*; list explicit columns instead."
                try:
                    tool.func = self._reject_select_star_wrapper(tool.func)
                except Exception:
                    pass

            elif tool.name == "sql_db_list_tables":
                tool.description = "List all available tables the database. Use this to discover which tables exist before querying."

            elif tool.name == "sql_db_schema":
                tool.description = "Retrieve the schema and sample rows for specific tables.Input: comma-separated list of valid table names."

        return tools
    
    def _get_engine(self):
        """
        Obtain the underlying SQLAlchemy engine from the SQLDatabase instance.
        """
        for attr in ("_engine", "engine"):
            eng = getattr(self.db, attr, None)
            if eng is not None:
                return eng
        get_eng = getattr(self.db, "get_engine", None)
        if callable(get_eng):
            return get_eng()
        raise RuntimeError("Could not find SQLAlchemy engine on SQLDatabase instance.")
