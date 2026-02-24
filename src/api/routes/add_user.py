from fastapi import APIRouter
from fastapi.params import Body

from src.api.schemas import AddNewUserResponse
from src.services import AddUserService

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.post("/add-new-user", response_model=AddNewUserResponse)
async def add_new_user(username: str = Body(..., embed=True)) -> dict:
    return await AddUserService(username=username)()
