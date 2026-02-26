from fastapi import APIRouter
from fastapi.params import Body
from starlette import status

from src.api.schemas import AddNewUserResponse
from src.services import AddUserService, RemoveUserService

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.post("/add-new-user", response_model=AddNewUserResponse)
async def add_new_user(username: str = Body(..., embed=True)) -> AddNewUserResponse:
    return await AddUserService(username=username)()


@router.post("/remove-user", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user(usernames: list[str] = Body(..., embed=True)) -> None:
    return await RemoveUserService(usernames=usernames)()
