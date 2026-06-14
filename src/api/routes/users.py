from fastapi import APIRouter
from fastapi.params import Body
from starlette import status

from src.api.schemas import AddNewUserResponse, GetUserResponse
from src.services import (
    AddUserService,
    GetUserService,
    RemoveUserService,
    RotateSecretService,
)

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/users/{username}", response_model=GetUserResponse)
async def get_user(username: str) -> GetUserResponse:
    return await GetUserService(username=username)()


@router.post("/users", response_model=AddNewUserResponse)
async def add_user(
    username: str = Body(..., embed=True),
    secret: str = Body(..., embed=True),
) -> AddNewUserResponse:
    return await AddUserService(username=username, secret=secret)()


@router.patch("/users", response_model=AddNewUserResponse)
async def rotate_secret(
    username: str = Body(..., embed=True),
    secret: str = Body(..., embed=True),
) -> AddNewUserResponse:
    return await RotateSecretService(username=username, secret=secret)()


@router.delete("/users", status_code=status.HTTP_204_NO_CONTENT)
async def remove_users(usernames: list[str] = Body(..., embed=True)) -> None:
    return await RemoveUserService(usernames=usernames)()
