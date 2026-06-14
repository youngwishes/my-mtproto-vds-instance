from pydantic import BaseModel


class GetUserResponse(BaseModel):
    username: str
    link: str
