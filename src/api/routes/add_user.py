from fastapi import APIRouter
from fastapi.params import Body

from src.services import AddUserService

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.post("/add-new-user")
async def add_new_user(username: str = Body(..., embed=True)) -> str:
    return await AddUserService(username=username)()
