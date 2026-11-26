from fastapi import APIRouter

from src.schemas.order import OrderResponse

router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])


@router.get("", response_model=list[OrderResponse])
async def list_orders():
    """Retrieve historical orders."""
    return []
