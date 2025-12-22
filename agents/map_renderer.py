"""
Map rendering utilities.
"""
import json
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium import plugins

class MapRenderer:
    """Handles map rendering with persistent zoom/pan state."""
    
    def __init__(self, icon_mapping_path: str = "feature_group_icons.json"):
        """
        Initialize the MapRenderer.
        
        Args:
            icon_mapping_path: Path to the JSON file with icon configurations
        """
        with open(icon_mapping_path, "r") as f:
            self.icon_mapping = json.load(f)
        
        #
        # Initialize session state variables if they don't exist.  st.session_state is
        # a global singleton thoughout the streamlit app
        #
        if "map_payload" not in st.session_state:
            st.session_state.map_payload = None
        if "map_view" not in st.session_state:
            st.session_state.map_view = None
    
    #
    # Streamlit fragment to render map.  Only this will rerun on map interactions.
    # Prevents agent spinning loop from starting again.
    #
    @st.fragment
    def _render_map_fragment(self, payload: dict):
        """
        Streamlit fragment to render map. Only this will rerun on map interactions.
        Prevents agent spinning loop from starting again.
        
        Args:
            payload: Dictionary containing map data with center and features
        """
        # Seed view from last interaction if we have it
        if st.session_state.map_view:
            init_center = st.session_state.map_view["center"]
            init_zoom = st.session_state.map_view["zoom"]
        else:
            c = payload["center"]
            init_center = [c["latitude"], c["longitude"]]
            init_zoom = 13

        m = folium.Map(
            location=init_center,
            zoom_start=init_zoom,
            control_scale=True,
        )

        # One parent FeatureGroup per top-level group
        parents = {}
        sublayers = {}  # (group, subgroup) -> FeatureGroupSubGroup

        locations = payload.get("features") or []
        for loc in locations:
            g = (loc.get("feature_group") or "default").strip()
            s = (loc.get("feature_subgroup") or "General").strip()

            if g not in parents:
                parents[g] = folium.FeatureGroup(name=g, show=True)
                parents[g].add_to(m)

            if (g, s) not in sublayers:
                sub = plugins.FeatureGroupSubGroup(parents[g], name=s, show=True)
                sub.add_to(m)
                sublayers[(g, s)] = sub

            icon_cfg = self.icon_mapping.get(g, self.icon_mapping["default"])
            folium.Marker(
                [loc["latitude"], loc["longitude"]],
                tooltip=loc.get("name") or "",
                icon=folium.Icon(
                    icon=icon_cfg["icon"], 
                    prefix="fa", 
                    color=icon_cfg["color"]
                ),
            ).add_to(sublayers[(g, s)])

        folium.LayerControl(collapsed=False).add_to(m)

        # Stable key so widget identity is preserved
        st_data = st_folium(m, width=700, height=500, key="my_map")

        # Remember the last view so zoom/pan persist across reruns
        if st_data and st_data.get("center") and st_data.get("zoom") is not None:
            st.session_state.map_view = {
                "center": [st_data["center"]["lat"], st_data["center"]["lng"]],
                "zoom": int(st_data["zoom"]),
            }
    
    def render_from_tool(self, map_tool):
        """
        Ingest new payload (if any) and render via the fragment.
        Call this OUTSIDE the spinner. Safe on reruns.
        
        Args:
            map_tool: The map tool instance that may contain new map data
        """
        # Pull a fresh payload exactly once per agent turn
        payload = None
        pop = getattr(map_tool, "pop_result", None)
        if callable(pop):
            payload = pop()  # dict or None
        else:
            # Fallback if pop_result doesn't exist: read & clear the attribute
            payload = getattr(map_tool, "_latest_result", None)
            if payload is not None:
                map_tool._latest_result = None  # prevent resetting zoom next rerun

        # If a new payload arrived, stash it and reset view for this new map
        if payload:
            st.session_state.map_payload = payload
            st.session_state.map_view = None

        # Always (re)render the current map; fragment preserves zoom/pan
        if st.session_state.map_payload:
            self._render_map_fragment(st.session_state.map_payload)