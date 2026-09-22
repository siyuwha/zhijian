from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from ...core.database import get_db
from ...services.simulation import SimulationService

router = APIRouter(prefix="/simulation", tags=["Forward Simulation"])

class AccountCreate(BaseModel):
    name: str
    initial_capital: float = 100000.0

@router.get("/accounts")
async def list_accounts(db: AsyncSession = Depends(get_db)):
    service = SimulationService(db)
    accounts = await service.get_accounts()
    return {"code": 200, "data": accounts}

@router.post("/accounts")
async def create_account(payload: AccountCreate, db: AsyncSession = Depends(get_db)):
    service = SimulationService(db)
    acc = await service.create_account(payload.name, payload.initial_capital)
    return {"code": 200, "data": acc}

@router.get("/accounts/{account_id}/positions")
async def list_sim_positions(account_id: int, db: AsyncSession = Depends(get_db)):
    service = SimulationService(db)
    positions = await service.get_positions(account_id)
    return {"code": 200, "data": positions}
