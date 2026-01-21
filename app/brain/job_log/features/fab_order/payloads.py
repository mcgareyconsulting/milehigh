from typing import Optional, TypedDict

class UpdateFabOrderRequest(TypedDict):
    fab_order: Optional[float]

class FabOrderChangePayload(TypedDict):
    from_order: Optional[float]
    to_order: Optional[float]