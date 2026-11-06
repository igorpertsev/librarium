from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import SessionDep
from app.schemas.library_settings import LibraryRules
from app.services import library_settings as settings_service

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/rules", response_model=LibraryRules)
async def library_rules(session: SessionDep) -> LibraryRules:
    """Batch size and price, loan period and how often a loan can be extended."""
    return LibraryRules.model_validate(await settings_service.get_library_settings(session))
