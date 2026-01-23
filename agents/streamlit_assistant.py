"""
Data Analytics Assistant - Main Streamlit Application
"""
import streamlit as st
import os

from react_agent import ReActAgent
from audit_agent import AuditAgent
from map_renderer import MapRenderer
from chart_renderer import ChartRenderer

##############################################################
#   Set up agent
##############################################################

# Read the DB URI from environment variable
db_uri = os.environ.get("DB_URI")
if not db_uri:
    st.error("No DB_URI found. Please set the DB_URI environment variable.")
    st.stop()

# Read the MCP URI from environment variable
mcp_uri = os.environ.get("MCP_URI")
if not mcp_uri:
    st.error("No MCP_URI found. Please set the MCP_URI environment variable.")
    st.stop()

# Initialize agent
agent = ReActAgent(
    db_uri=db_uri,
    mcp_uri=mcp_uri,
    model_name="gpt-5-mini",
    max_iterations=10,
    system_prompt_path="agent_system_prompt.txt"
)

# Initialize audit agent
audit_agent = AuditAgent(model_name="gpt-4o", temperature=0.0)

# Initialize renderers
map_renderer = MapRenderer(icon_mapping_path="feature_group_icons.json")
chart_renderer = ChartRenderer()

##############################################################
#   Streamlit App
##############################################################

# Title
st.title("🧠 Data Analytics Assistant")

#
# Check or reset message history then show all past messages
#
if "messages" not in st.session_state or st.sidebar.button("Clear message history"):
    st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you?"}]
    st.session_state["last_result"] = None

for msg in st.session_state.messages:
    st.write(f"**{msg['role'].capitalize()}:** {msg['content']}")

#
# Get user input
#
prompt = st.text_area(
    "Enter a data analysis request and hit Submit",
    value="Very briefly, how can you help analyze the database and geographic features using statistical methods and visualizations?",
    height=200,
)

# Add a submit button to explicitly control when the agent runs
submit_button = st.button("Submit Request", type="secondary")

#
# Write response, run chart if generated, render map if map data
#
if submit_button and prompt:
    with st.spinner("Working on it..."):
        try:
            #
            # Write the input to messages
            #
            st.session_state.messages.append({"role": "user", "content": prompt})

            #
            # Run the agent and get the response and intermediate steps
            #
            result = agent.run(prompt) 
            intermediate_steps = result.get("intermediate_steps", [])
            final_output = result.get("output", "")
            
            # Store result for audit
            st.session_state["last_result"] = {
                "prompt": prompt,
                "result": result,
                "tool_descriptions": agent.get_tool_descriptions_text()
            }
            
            #
            # Show the intermediate steps
            #
            if intermediate_steps:
                st.subheader("🧩 Intermediate Reasoning Steps")
                for i, step in enumerate(intermediate_steps):
                    st.markdown(f"**Step {i+1}:**")
                    st.markdown(f"- **Action:** `{step[0].tool}`")
                    st.markdown(f"- **Tool Input:** `{step[0].tool_input}`")
                    # Trim observations longer than 5 lines and append notice
                    obs = step[1]
                    obs_lines = str(obs).splitlines()
                    if len(obs_lines) > 5:
                        obs = "\n".join(obs_lines[:5]) + "\n......trimmed to 5 lines"
                    st.markdown(f"- **Observation:**")
                    st.code(obs)
            
            #
            #  Add the response to history
            #
            st.session_state.messages.append({"role": "assistant", "content": final_output})
            
            #
            # Show the response
            #
            st.subheader("💬 Final Answer")
            st.markdown(final_output)
            
            #
            # If chart code was generated, render it
            #
            chart_tool = agent.get_chart_tool()
            chart_renderer.render_from_tool(chart_tool)

        except Exception as e:
            st.error(f"An error occurred: {e}")
                        
    #
    # If map data was generated, render map (outside spinner)
    #
    map_tool = agent.get_map_tool()
    map_renderer.render_from_tool(map_tool)

#
# Audit button - only show if there's a result to audit
#
if st.session_state.get("last_result") is not None:
    st.divider()
    if st.button("🔍 Run Audit", type="primary"):
        last = st.session_state["last_result"]
        
        with st.spinner("Conducting audit..."):
            try:
                st.subheader("🔍 Audit Report")
                audit_report = audit_agent.audit(
                    tool_descriptions=last["tool_descriptions"],
                    user_prompt=last["prompt"],
                    intermediate_steps=last["result"].get("intermediate_steps", []),
                    final_answer=last["result"].get("output", "")
                )
                st.markdown(audit_report)
                st.caption(f"*Audited by: {audit_agent.llm.model_name}*")
            except Exception as audit_error:
                st.error(f"Audit failed: {audit_error}")
