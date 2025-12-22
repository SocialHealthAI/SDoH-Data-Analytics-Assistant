"""
Chart rendering.
"""
import contextlib
import io
import streamlit as st
import matplotlib.pyplot as plt


class ChartRenderer:
    """Handles chart rendering from generated code."""
    
    @staticmethod
    def render_from_tool(chart_tool):
        """
        Execute and display chart code if available from the chart tool.
        
        Args:
            chart_tool: The chart tool instance that may contain generated chart code
        """
        if not hasattr(chart_tool, "_latest_result") or not chart_tool._latest_result:
            return
        
        result = chart_tool._latest_result
        code_block = result.get("code_block")

        if not code_block:
            st.info("No chart code was generated in the response.")
            return

        st.subheader("📊 Chart")
        st.markdown(result.get("explanation"))

        try:
            # Always reset the matplotlib state
            plt.close('all')

            # Strip close if included in code so it isn't closed before we present with plt.gcf()
            code_block = code_block.replace("\nplt.close()", "")

            local_vars = {"plt": plt, "__builtins__": __builtins__}
            with contextlib.redirect_stdout(io.StringIO()):
                exec(code_block, local_vars)

            # Force matplotlib to finalize any figure created
            fig = plt.gcf()

            if fig and fig.get_axes():
                st.pyplot(fig)
            else:
                st.warning("No chart was generated. The code ran, but no figure was created.")

        except Exception as e:
            st.error(f"Error running chart code: {e}")