from langchain.tools import StructuredTool
from pydantic import BaseModel, Field, AliasChoices, model_validator
from typing import List, Optional, Dict, Any

# ----------------------------
# Schemas
# ----------------------------
class Location(BaseModel):
    name: str = Field("Unknown", description="Name of the location")
    latitude: float = Field(
        ...,
        description="Latitude of the location",
        validation_alias=AliasChoices("lat", "latitude"),
    )
    longitude: float = Field(
        ...,
        description="Longitude of the location",
        validation_alias=AliasChoices("lon", "long", "lng", "longitude"),
    )
    feature_group: Optional[str] = Field(
        None, description="High-level category (e.g., 'healthcare', 'environment')"
    )
    feature_subgroup: Optional[str] = Field(
        None,
        description="More specific subgroup (e.g., 'clinic', 'park')",
        validation_alias=AliasChoices("feature_subgroup", "sub_feature_group"),
    )

    model_config = {"populate_by_name": True}


class MapDataToolInput(BaseModel):
    # Accept common mistakes/aliases and fix them in a pre-validator
    center: Location = Field(
        ...,
        description="Required map center (name, latitude, longitude)",
        validation_alias=AliasChoices(
            "center",
            '"center"',
            ' "center"',
            '\n "center"',
            "location",  # upstream sometimes calls this 'location'
        ),
    )
    features: List[Location] = Field(
        ...,
        description="List of points of interest to display",
        validation_alias=AliasChoices(
            "features",
            '"features"',
            ' "features"',
            '\n "features"',
            "locations",  # sometimes tools emit 'locations'
            "points",
            "markers",
        ),
    )

    @model_validator(mode="before")
    def _normalize(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(values, dict):
            return values

        # 1) Normalize outer keys (strip whitespace/quotes)
        def _normalize_key(k: str) -> str:
            return k.strip().strip('"') if isinstance(k, str) else k

        fixed = {}
        for k, v in values.items():
            nk = _normalize_key(k)
            fixed[nk] = v
        values = fixed

        # 2) Support 'location' -> 'center'
        if "location" in values and "center" not in values:
            values["center"] = values.pop("location")

        # 3) Flatten nested {"coordinates": {lat, lon}} for center & each feature
        def _flatten_coords(d: Dict[str, Any]):
            if not isinstance(d, dict):
                return
            coords = d.get("coordinates")
            if isinstance(coords, dict):
                d.setdefault("latitude", coords.get("latitude") or coords.get("lat"))
                d.setdefault(
                    "longitude",
                    coords.get("longitude") or coords.get("lon") or coords.get("lng"),
                )
            # Normalize subgroup alias
            if "feature_subgroup" not in d and "sub_feature_group" in d:
                d["feature_subgroup"] = d["sub_feature_group"]

        if isinstance(values.get("center"), dict):
            _flatten_coords(values["center"])

        feats = values.get("features")
        if isinstance(feats, list):
            for f in feats:
                if isinstance(f, dict):
                    _flatten_coords(f)

        return values


# ----------------------------
# Tool wrapper
# ----------------------------
class MapDataTool:
    """
    LangChain StructuredTool wrapper to package map center + features for your UI.
    Stores the latest result in self._latest_result so your Streamlit layer can pop it once.
    """

    def __init__(self):
        self._latest_result: Optional[Dict[str, Any]] = None

        self.tool = StructuredTool.from_function(
            func=self._run,
            name="mapdata_tool",
            description=(
                "Transform geographic features from neighborhood tools into a structure suitable for displaying a map. Features have (name, latitude, longitude, 'feature_group', feature_subgroup')"
            ),
            args_schema=MapDataToolInput,
            return_direct=True,  # terminate the chain after tool call
        )

    def _run(self, center: Location, features: List[Location]) -> str:
        result = {
            "center": center.model_dump(),
            "features": [loc.model_dump() for loc in features],
        }
        self._latest_result = result
        return "Map ready. The app will render the interactive map."

    def pop_result(self) -> Optional[Dict[str, Any]]:
        result = self._latest_result
        self._latest_result = None
        return result
