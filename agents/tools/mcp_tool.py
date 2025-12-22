from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.tools import StructuredTool
import asyncio

class McpTool:
    """
    Sync-friendly MCP tool loader for LangChain agents.
    Filters out MCP-injected `ctx` so LangChain can use the tool cleanly.
    """

    def __init__(self, server_name: str, mcp_url: str):
        self.server_name = server_name
        self.mcp_url = mcp_url

    def get_tool(self, tool_name: str):
        async def _load():
            client = MultiServerMCPClient({
                self.server_name: {
                    "url": self.mcp_url,
                    "transport": "streamable_http"
                }
            })
            async with client.session(self.server_name) as session:
                tools = await client.get_tools(server_name=self.server_name)
                for t in tools:
                    if t.name == tool_name:
                        # Wrap with a sync StructuredTool
                        def sync_func(**tool_kwargs):
                            # 🚨 Remove ctx before calling the async tool
                            tool_kwargs.pop("ctx", None)
                            return asyncio.run(t.ainvoke(tool_kwargs))

                        return StructuredTool.from_function(
                            name=t.name,
                            description=t.description,
                            func=sync_func,
                            args_schema=t.args_schema,
                        )
            return None

        return asyncio.run(_load())

