#from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Context
from fastmcp import FastMCP
from dataclasses import dataclass
from typing import AsyncIterator, List, Dict, Optional, Tuple, Any, Union
import aiohttp
import json
import asyncio
from contextlib import asynccontextmanager
import math
from datetime import datetime


#
# Use standard logging instead of ctx.report_progress(), ctx.info(), and ctx.warning()
# Support for these are injected by MCP Context management which we are not using.
#
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

#
# Open Street Mapping API
#
class OSMClient:
    def __init__(self, base_url="https://api.openstreetmap.org/api/0.6"):
        self.base_url = base_url
        self.session = None
        self.cache = {}  # Simple in-memory cache
    
    async def connect(self):
        self.session = aiohttp.ClientSession()
        
    async def disconnect(self):
        if self.session:
            await self.session.close()

    async def geocode(self, query: str) -> List[Dict]:
        """Geocode an address or place name"""
        if not self.session:
            raise RuntimeError("OSM client not connected")
        
        nominatim_url = "https://nominatim.openstreetmap.org/search"
        async with self.session.get(
            nominatim_url,
            params={
                "q": query,
                "format": "json",
                "limit": 5
            },
            headers={"User-Agent": "OSM-MCP-Server/1.0"}
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise Exception(f"Failed to geocode '{query}': {response.status}")
    
    async def reverse_geocode(self, lat: float, lon: float) -> Dict:
        """Reverse geocode coordinates to address"""
        if not self.session:
            raise RuntimeError("OSM client not connected")
        
        nominatim_url = "https://nominatim.openstreetmap.org/reverse"
        async with self.session.get(
            nominatim_url,
            params={
                "lat": lat,
                "lon": lon,
                "format": "json"
            },
            headers={"User-Agent": "OSM-MCP-Server/1.0"}
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise Exception(f"Failed to reverse geocode ({lat}, {lon}): {response.status}")

    async def get_route(self, 
                         from_lat: float, 
                         from_lon: float, 
                         to_lat: float, 
                         to_lon: float,
                         mode: str = "car",
                         steps: bool = False,
                         overview: str = "overview",
                         annotations: bool = True) -> Dict:
        """Get routing information between two points"""
        if not self.session:
            raise RuntimeError("OSM client not connected")
        
        # Use OSRM for routing
        osrm_url = f"http://router.project-osrm.org/route/v1/{mode}/{from_lon},{from_lat};{to_lon},{to_lat}"
        params = {
            "overview": overview,
            "geometries": "geojson",
            "steps": str(steps).lower(),
            "annotations": str(annotations).lower()
        }
        
        async with self.session.get(osrm_url, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise Exception(f"Failed to get route: {response.status}")

    async def get_nearby_pois(self, 
                             lat: float, 
                             lon: float, 
                             radius: float = 1000,
                             categories: List[str] = None) -> List[Dict]:
        """Get points of interest near a location"""
        if not self.session:
            raise RuntimeError("OSM client not connected")
        
        # Convert radius to bounding box (approximate)
        # 1 degree latitude ~= 111km
        # 1 degree longitude ~= 111km * cos(latitude)
        lat_delta = radius / 111000
        lon_delta = radius / (111000 * math.cos(math.radians(lat)))
        
        bbox = (
            lon - lon_delta,
            lat - lat_delta,
            lon + lon_delta,
            lat + lat_delta
        )
        
        # Build Overpass query
        overpass_url = "https://overpass-api.de/api/interpreter"
        
        # Default to common POI types if none specified
        if not categories:
            categories = ["amenity", "shop", "tourism", "leisure"]
        
        # Build tag filters
        tag_filters = []
        for category in categories:
            tag_filters.append(f'node["{category}"]({{bbox}});')
        
        query = f"""
        [out:json];
        (
            {" ".join(tag_filters)}
        );
        out body;
        """
        
        query = query.replace("{bbox}", f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}")
        
        async with self.session.post(overpass_url, data={"data": query}) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("elements", [])
            else:
                raise Exception(f"Failed to get nearby POIs: {response.status}")

    async def search_features_by_category(self, 
                                         bbox: Tuple[float, float, float, float],
                                         category: str,
                                         subcategories: List[str] = None) -> List[Dict]:
        """Search for OSM features by category and subcategories"""
        if not self.session:
            raise RuntimeError("OSM client not connected")
        
        overpass_url = "https://overpass-api.de/api/interpreter"
        
        # Build query for specified category and subcategories
        if subcategories:
            subcategory_filters = " or ".join([f'"{category}"="{sub}"' for sub in subcategories])
            query_filter = f'({subcategory_filters})'
        else:
            query_filter = f'"{category}"'
        
        query = f"""
        [out:json];
        (
          node[{query_filter}]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
          way[{query_filter}]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
          relation[{query_filter}]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
        );
        out body;
        """
        
        async with self.session.post(overpass_url, data={"data": query}) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("elements", [])
            else:
                raise Exception(f"Failed to search features by category: {response.status}")

# ---------------------------
# MCP Server setup
# ---------------------------

# Create application context
@dataclass
class AppContext:
    osm_client: OSMClient

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    osm_client = OSMClient()
    try:
        await osm_client.connect()
        ctx = AppContext(osm_client=osm_client)
        server.app_context = ctx
        yield ctx
    finally:
        await osm_client.disconnect()
        server.app_context = None

# Create the MCP server.  Tools will be served at /api
# (fastmcp>=2.14 removed the `dependencies=` constructor arg; declare packages in pyproject.toml / image instead.)
mcp = FastMCP(
    "Location-Based App MCP Server",
    lifespan=app_lifespan,
)

# add a slot for context
mcp.app_context = None

# And the manifest for the Minimal (or Simple) MCP protocol is used in MCP-based systems and agents 
# like fastmcp, mcp-agents, Continue, react, etc. It is served at
# "/.well-known/ai-plugin.json"

# FastMCP includes an internal ToolManager, which lives in fastmcp.tools.tool_manager.
# However, this manager is not directly exposed as an attribute of your mcp instance.
# So there is no public API on mcp that lets you iterate over registered tools via a .tool_manager or .tools property.

# ---------------------------
# Custom Metadata Method.  No longer needed
# ---------------------------

@mcp.resource("plugin://ai-plugin/manifest")
def manifest():
    return {
        "name": mcp.name,
        "tools": [
            {
                "name": "analyze_neighborhood",
                "description": "Search around a geographic point to identify nearby establishments, amenities, and points of interest for location-based recommendations, neighborhood analysis, and proximity-based decision making",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "latitude": {"type": "number"},
                        "longitude": {"type": "number"},
                        "radius": {"type": "number"},
                        "categories": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["latitude", "longitude"]
                }
            }
        ]
    }


# ---------------------------
# Analyze Neighborhood Tool
#
# Note for langchain clients using tools below:
# MultiServerMCPClient.get_tools(server_name) takes the list_tools output and wraps each entry into a LangChain StructuredTool.
# The args_schema in that StructuredTool comes from tool’s JSON Schema in input_schema.
# Name
# Description
# Parameters + types
# Required fields
#
# ---------------------------

# Helper: pick a reasonable subgroup from OSM tags.
# Primary intent is to expose 'amenity' as 'sub_feature_group'.
# When 'amenity' is absent, we fall back to other common keys so categories
# like 'shop=*' or 'leisure=*' still get a subgroup label.
def _derive_sub_feature_group(tags: Dict[str, Any]) -> Optional[str]:
    for k in (
        "amenity", "shop", "leisure", "public_transport", "railway",
        "highway", "landuse", "building", "emergency"
    ):
        if k in tags and tags[k]:
            return tags[k]
    return None


@mcp.tool()
async def analyze_neighborhood(
    latitude: float,
    longitude: float,
    radius: float = 1000,
) -> Dict[str, Any]:
    """
    Search around a geographic point to identify nearby features and metric-groups
    important to Social Determinants of Health (SDOH). Returns:
      - scores.overall
      - scores.walkability
      - scores.metric_groups: per-metric-group score dict
      - metric_groups: per-metric-group results with features + metrics
    Each feature includes:
      - feature_group: the metric-group name (e.g., "education")
      - sub_feature_group: 
    """

    if not mcp.app_context:
        raise RuntimeError("App context not available")

    osm_client = mcp.app_context.osm_client

    # Reverse geocode the center point
    address_info = await osm_client.reverse_geocode(latitude, longitude)

    # Categories aligned with SDOH (unchanged)
    categories = [
        {"name": "healthcare", "tags": [
            "amenity=hospital", "amenity=clinic", "amenity=doctors",
            "amenity=dentist", "amenity=pharmacy", "amenity=health_post"
        ]},
        {"name": "education", "tags": [
            "amenity=school", "amenity=kindergarten", "amenity=college",
            "amenity=university", "amenity=library"
        ]},
        {"name": "food_access", "tags": [
            "shop=supermarket", "shop=convenience", "shop=grocery",
            "amenity=food_bank", "amenity=marketplace"
        ]},
        {"name": "economic_stability", "tags": [
            "amenity=bank", "amenity=atm", "amenity=post_office",
            "shop=mall", "shop=department_store", "shop=clothes"
        ]},
        {"name": "housing", "tags": [
            "building=apartments", "building=house", "building=residential",
            "amenity=social_facility"
        ]},
        {"name": "transportation", "tags": [
            "public_transport=stop_position", "railway=station", "amenity=bus_station",
            "highway=bus_stop", "amenity=bicycle_rental", "amenity=car_rental"
        ]},
        {"name": "environment", "tags": [
            "leisure=park", "leisure=garden", "leisure=playground",
            "leisure=nature_reserve", "landuse=forest"
        ]},
        {"name": "community", "tags": [
            "amenity=community_centre", "amenity=place_of_worship",
            "amenity=social_centre", "amenity=theatre", "amenity=arts_centre"
        ]},
        {"name": "safety", "tags": [
            "amenity=police", "amenity=fire_station", "amenity=townhall",
            "emergency=ambulance_station", "emergency=fire_hydrant"
        ]},
    ]

    metric_groups: Dict[str, Any] = {}
    scores: Dict[str, float] = {}

    # Precompute lat/lon deltas for bbox
    lat_delta = radius / 111_000.0
    lon_delta = radius / (111_000.0 * math.cos(math.radians(latitude)))
    bbox = (
        longitude - lon_delta,
        latitude - lat_delta,
        longitude + lon_delta,
        latitude + lat_delta,
    )

    overpass_url = "https://overpass-api.de/api/interpreter"

    for category in categories:
        cat_name = category["name"]
        logger.info(f"Analyzing {cat_name} in neighborhood...")

        # Build Overpass query for this category
        tag_filters = []
        for tag in category["tags"]:
            key, value = tag.split("=")
            tag_filters.append(f'node["{key}"="{value}"]({{bbox}});')
            tag_filters.append(f'way["{key}"="{value}"]({{bbox}});')
            tag_filters.append(f'relation["{key}"="{value}"]({{bbox}});')  # include relations too

        query = f"""
        [out:json][timeout:25];
        (
            {" ".join(tag_filters)}
        );
        /* Return centroid for ways/relations so we can compute distances */
        out center;
        """
        query = query.replace("{bbox}", f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}")

        try:
            async with aiohttp.ClientSession() as session:  # kept as-is per your earlier preference
                async with session.post(overpass_url, data={"data": query}) as response:
                    if response.status == 200:
                        data = await response.json()
                        elements = data.get("elements", [])
                    else:
                        logger.warning(f"Failed to analyze {cat_name}: HTTP {response.status}")
                        elements = []

            # Process elements -> features
            feature_list = []
            distances = []

            # Local haversine (meters)
            from math import radians, sin, cos, sqrt, asin

            def haversine(lat1, lon1, lat2, lon2):
                R = 6_371_000.0
                dLat = radians(lat2 - lat1)
                dLon = radians(lon2 - lon1)
                a = sin(dLat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dLon / 2) ** 2
                c = 2 * asin(sqrt(a))
                return R * c

            for el in elements:
                tags = el.get("tags", {}) or {}
                coords = {}

                if el.get("type") == "node":
                    lat = el.get("lat")
                    lon = el.get("lon")
                    if lat is not None and lon is not None:
                        coords = {"latitude": lat, "longitude": lon}
                else:
                    center = el.get("center") or {}
                    lat = center.get("lat")
                    lon = center.get("lon")
                    if lat is not None and lon is not None:
                        coords = {"latitude": lat, "longitude": lon}

                if not coords:
                    continue

                dist_m = haversine(latitude, longitude, coords["latitude"], coords["longitude"])
                distances.append(dist_m)

                feature_list.append({
                    "id": el.get("id"),
                    "name": tags.get("name", "Unnamed"),
                    "type": el.get("type"),
                    "coordinates": coords,
                    "distance": round(dist_m, 1),
                    "tags": tags,  # keep original OSM tags intact
                    # --- NEW FIELDS ---
                    "feature_group": cat_name,  # metric-group name
                    "sub_feature_group": _derive_sub_feature_group(tags),  # amenity -> subgroup (fallbacks supported)
                })

            feature_list.sort(key=lambda x: x["distance"])

            count = len(feature_list)
            avg_distance = (sum(distances) / count) if count > 0 else None
            min_distance = (min(distances) if count > 0 else None)

            # Simple scoring: supply + proximity (unchanged)
            if count == 0:
                category_score = 0.0
            else:
                count_score = min(count / 5.0, 1.0) * 5.0
                proximity_score = 5.0 - min((min_distance or radius) / radius, 1.0) * 5.0
                category_score = count_score + proximity_score

            metric_groups[cat_name] = {
                "count": count,
                "features": feature_list[:10],
                "metrics": {
                    "total_count": count,
                    "avg_distance": round(avg_distance, 1) if avg_distance is not None else None,
                    "min_distance": round(min_distance, 1) if min_distance is not None else None,
                },
            }
            scores[cat_name] = category_score

        except Exception as e:
            logger.warning(f"Error analyzing {cat_name}: {str(e)}")
            metric_groups[cat_name] = {"error": str(e)}
            scores[cat_name] = 0.0

    # Overall + walkability
    overall_score = (sum(scores.values()) / len(scores)) if scores else 0.0

    walkable_amenities = 0
    walkable_categories = 0
    for cat_name, cat_data in metric_groups.items():
        if isinstance(cat_data, dict) and "metrics" in cat_data:
            walking_count = sum(
                1 for f in cat_data.get("features", []) if f.get("distance", float("inf")) <= 500.0
            )
            if walking_count > 0:
                walkable_amenities += walking_count
                walkable_categories += 1

    walkability_score = min(walkable_amenities + walkable_categories, 10)

    return {
        "center": {
            "coordinates": {"latitude": latitude, "longitude": longitude},
            "address": address_info.get("display_name", "Unknown location"),
        },
        "scores": {
            "overall": round(overall_score, 1),
            "walkability": walkability_score,
            # RENAMED: feature_groups -> metric_groups (per your request)
            "metric_groups": {k: round(v, 1) for k, v in scores.items()},
        },
        # RENAMED: feature_groups -> metric_groups (per your request)
        "metric_groups": metric_groups,
        "analysis_radius": radius,
        "timestamp": datetime.now().isoformat(),
    }

# ---------------------------
# Entry point
# ---------------------------
if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    mcp.run(transport="http", host="0.0.0.0", port=port)