"""
SDoH Data Analytics Assistant - Main Streamlit Application
"""
import streamlit as st
import os
import re

from react_agent import ReActAgent
from audit_agent import AuditAgent
from map_renderer import MapRenderer
from chart_renderer import ChartRenderer

st.set_page_config(page_title="SDoH Data Analytics Assistant")

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
#   Streamlit App Logic
##############################################################

def escape_markdown(text):
    """Escape markdown special characters but preserve tables and intentional formatting."""
    # Escape lines that are purely === or --- (common in statistical output)
    text = re.sub(r'^(=+)$', r'\\\1', text, flags=re.MULTILINE)
    text = re.sub(r'^(-+)$', r'\\\1', text, flags=re.MULTILINE)
    
    # Escape lines that start with *** or ___ (alternative horizontal rules)
    text = re.sub(r'^(\*{3,})$', r'\\\1', text, flags=re.MULTILINE)
    text = re.sub(r'^(_{3,})$', r'\\\1', text, flags=re.MULTILINE)
    
    # Escape # at start of lines (headers)
    text = re.sub(r'^(#{1,6})\s', r'\\\1 ', text, flags=re.MULTILINE)
    
    return text


st.title("🧠 SDoH Data Analytics Assistant")

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you?"}]
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None
if "show_audit" not in st.session_state:
    st.session_state["show_audit"] = False
if "show_steps" not in st.session_state:
    st.session_state["show_steps"] = False

# --- SIDEBAR ---
with st.sidebar:
    st.header("Controls")
    
    if st.button("Clear message history", use_container_width=True):
        st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you?"}]
        st.session_state["last_result"] = None
        st.session_state["show_audit"] = False
        st.session_state["show_steps"] = False
        st.rerun()

    if st.session_state["last_result"] is not None:
        st.divider()
        st.subheader("Analysis Tools")
        
        # Toggle buttons
        if st.button("🧩 View Logic Steps", use_container_width=True):
            st.session_state["show_steps"] = not st.session_state["show_steps"]
            st.session_state["show_audit"] = False
            
        if st.button("🔍 Run Audit", type="secondary", use_container_width=True):
            st.session_state["show_audit"] = True
            st.session_state["show_steps"] = False

# --- MAIN CHAT AREA ---

# 1. Display Message History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 2. PERSISTENT CHART RENDERING
# Only render if we're not showing steps or audit (which would interfere)
if st.session_state["last_result"] and st.session_state["last_result"].get("chart_code"):
    if not st.session_state["show_steps"] and not st.session_state["show_audit"]:
        chart_code = st.session_state["last_result"]["chart_code"]
        explanation = st.session_state["last_result"]["result"].get("explanation")
        chart_renderer.render_from_code(chart_code, explanation=None)

# 3. Logic Steps Display with Header
if st.session_state["show_steps"] and st.session_state["last_result"]:
    st.divider()
    st.header("🧩 Logic Steps")
    steps = st.session_state["last_result"]["result"].get("intermediate_steps", [])
    
    for i, step in enumerate(steps):
        with st.expander(f"Step {i+1}: {step[0].tool}", expanded=True):
            st.markdown(f"**Action Input:** `{step[0].tool_input}`")
            obs = str(step[1])
            if len(obs.splitlines()) > 5:
                obs = "\n".join(obs.splitlines()[:5]) + "\n... (truncated)"
            st.code(obs)

# 4. Audit Display
if st.session_state["show_audit"] and st.session_state["last_result"]:
    st.divider()
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
        except Exception as e:
            st.error(f"Audit failed: {e}")

# --- INPUT AREA ---

prompt = st.chat_input("Ask me about SDoH topics in the database")

if prompt:
    st.session_state["show_audit"] = False
    st.session_state["show_steps"] = False
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.spinner("Processing..."):
        try:
            result = agent.run(prompt)
            
            # Capture the chart code IMMEDIATELY before rerunning
            chart_tool = agent.get_chart_tool()
            saved_chart_code = None
            
            if chart_tool and hasattr(chart_tool, '_latest_result'):
                latest_result = chart_tool._latest_result
                if latest_result:
                    saved_chart_code = latest_result.get("code_block")
            
            st.session_state["last_result"] = {
                "prompt": prompt,
                "result": result,
                "tool_descriptions": agent.get_tool_descriptions_text(),
                "chart_code": saved_chart_code  # This should now have the actual code!
            }
            
            st.session_state.messages.append({
                "role": "assistant", 
                "content": escape_markdown(result.get("output", ""))
            })

            st.rerun()
            
        except Exception as e:
            st.error(f"Error: {e}")