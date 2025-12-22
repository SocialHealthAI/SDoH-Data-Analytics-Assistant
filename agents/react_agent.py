import os
from typing import List, Optional, Dict, Any

from langchain.agents import load_tools
from langchain_openai import ChatOpenAI

from agent_types import OpenAIToolCallingAgent
from tools.mcp_tool import McpTool
from tools.dictionary_tool import DictionaryLocalTool
from tools.sql_db_list_stat_func_tool import SQLDBListStatFuncTool
from tools.chart_tool import ChartTool
from tools.search_tool import SearchTool
from tools.sql_tool import SQLTools
from tools.mapdata_tool import MapDataTool


class ReActAgent:
    """
    Class for ReAct Agent, handles initialization of the LLM, tools, and the agent itself.
    """
    
    def __init__(
        self,
        db_uri: str,
        mcp_uri: str,
        model_name: str = "gpt-5-mini",
        temperature: float = 0.0,
        max_iterations: int = 10,
        system_prompt_path: str = "agent_system_prompt.txt"
    ):
        """
        Initialize the ReAct Agent with all required tools.
        
        Args:
            db_uri: Database connection URI
            mcp_uri: MCP server URI
            model_name: OpenAI model name
            temperature: LLM temperature setting
            max_iterations: Maximum agent iterations
            system_prompt_path: Path to system prompt file
        """
        self.db_uri = db_uri
        self.mcp_uri = mcp_uri
        self.model_name = model_name
        self.temperature = temperature
        self.max_iterations = max_iterations
        
        # Load system prompt
        self.system_prompt = self._load_system_prompt(system_prompt_path)
        
        # Initialize LLM
        self.llm = ChatOpenAI(model=model_name, temperature=temperature)
        
        # Initialize tools
        self.chart_tool = None
        self.search_tool = None
        self.map_data_tool = None
        self.tools = self._initialize_tools()
        
        # Initialize agent
        self.agent = OpenAIToolCallingAgent(
            tools=self.tools,
            llm=self.llm,
            max_iterations=max_iterations
        )
    
    def _load_system_prompt(self, path: str) -> str:
        """Load the system prompt from file."""
        try:
            with open(path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            print(f"Warning: System prompt file not found at {path}. Using empty prompt.")
            return ""
    
    def _initialize_tools(self) -> List:
        """
        Initialize all tools required by the agent.
        
        Returns:
            List of initialized tools
        """
        all_tools = []
        
        # 1. Chart Tool
        self.chart_tool = ChartTool(llm=self.llm)
        
        # 2. Internet Search Tool (conditional)
        tavily_api_key = os.environ.get("TAVILY_API_KEY")
        if tavily_api_key and tavily_api_key.strip():
            self.search_tool = SearchTool()
        
        # 3. Community Tools (LLM Math)
        community_tools = load_tools(['llm-math'], llm=self.llm)
        all_tools.extend(community_tools)
        
        # 4. Dictionary Tool
        dictionary_tool = DictionaryLocalTool(
            persist_dir="../../../workspace/data",
            model_name="all-MiniLM-L6-v2",
            search_k=6
        ).get_tool()
        
        # 5. SQL Tools
        sql_tools_obj = SQLTools(db_uri=self.db_uri, llm=self.llm)
        sql_tools = sql_tools_obj.get_tools()
        all_tools.extend(sql_tools)
        
        # 6. SQL DB List Statistics Function Tool
        sql_db_list_stat_func_tool = SQLDBListStatFuncTool(
            parent=sql_tools_obj,
            schema="public",
            prefix=""
        )
        
        # 7. MCP Tools
        mcp_tool_loader = McpTool(server_name='OSM', mcp_url=self.mcp_uri)
        mcp_tool = mcp_tool_loader.get_tool("analyze_neighborhood")
        
        # 8. Map Data Tool
        map_data = MapDataTool()
        self.map_data_tool = map_data  # Store reference for later access
        map_data_tool = map_data.tool
        
        # Build final tools list
        tools_list = [
            sql_db_list_stat_func_tool,
            self.chart_tool,
            mcp_tool,
            map_data_tool,
            dictionary_tool
        ]
        
        # Add search tool if available
        if self.search_tool is not None:
            tools_list.append(self.search_tool)
        
        all_tools.extend(tools_list)
        
        return all_tools
    
    def run(self, user_prompt: str, include_system_prompt: bool = True) -> Dict[str, Any]:
        """
        Run the agent with a user prompt.
        
        Args:
            user_prompt: The user's query/request
            include_system_prompt: Whether to prepend the system prompt
            
        Returns:
            Dict containing 'output' and 'intermediate_steps'
        """
        if include_system_prompt and self.system_prompt:
            full_prompt = f"{self.system_prompt}\n\nUser request:\n{user_prompt}"
        else:
            full_prompt = user_prompt
        
        result = self.agent.run(full_prompt)
        return result
    
    def get_chart_tool(self) -> Optional[ChartTool]:
        """Get reference to the chart tool for rendering."""
        return self.chart_tool
    
    def get_map_tool(self) -> Optional[MapDataTool]:
        """Get reference to the map data tool for rendering."""
        return self.map_data_tool
    
    def get_tool_descriptions_text(self) -> str:
        """
        Return a plain-text description of all tools available to the agent.
        """
        sections = []

        for idx, tool in enumerate(self.tools, start=1):
            # ---- Tool name ----
            if hasattr(tool, "name"):
                name = tool.name
            else:
                name = tool.__class__.__name__

            # ---- Description ----
            if hasattr(tool, "description") and tool.description:
                description = tool.description
            elif tool.__doc__:
                description = tool.__doc__
            else:
                description = "No description provided."

            # Normalize whitespace for LLMs
            description = " ".join(description.strip().split())

            section = (
                f"Tool {idx}: {name}\n"
                f"Purpose: {description}"
            )

            sections.append(section)

        return "\n\n".join(sections)
