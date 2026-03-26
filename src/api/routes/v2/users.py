from fastapi import APIRouter
from fastapi.params import Body
from starlette import status

from src.api.schemas import AddNewUserResponse
from src.services import AddUserServiceV2, RemoveUserServiceV2

router = APIRouter(prefix="/api/v2", tags=["users"])


@router.post("/users/add", response_model=AddNewUserResponse)
async def add_new_user(
    username: str = Body(..., embed=True),
    secret: str = Body(..., embed=True)
) -> AddNewUserResponse:
    return await AddUserServiceV2(username=username, secret=secret)()


@router.post("/users/remove", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user(usernames: list[str] = Body(..., embed=True)) -> None:
    return await RemoveUserServiceV2(usernames=usernames)()
