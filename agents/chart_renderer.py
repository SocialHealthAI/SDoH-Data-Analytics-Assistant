"""
Chart rendering.
"""
import contextlib
import io
import streamlit as st
import matplotlib.pyplot as plt

from langchain_experimental.utilities import PythonREPL


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
            # Reset matplotlib state
            plt.close("all")

            # Prevent premature closing of figures
            code_block = code_block.replace("\nplt.close()", "")

            # Initialize Python REPL with a controlled local scope
            repl = PythonREPL(
                locals={
                    "plt": plt,
                }
            )

            # Suppress stdout from the REPL execution
            with contextlib.redirect_stdout(io.StringIO()):
                repl.run(code_block)

            # Retrieve the active figure
            fig = plt.gcf()

            if fig and fig.get_axes():
                st.pyplot(fig)
            else:
                st.warning(
                    "No chart was generated. The code ran, but no figure was created."
                )

        except Exception as e:
            st.error(f"Error running chart code: {e}")
