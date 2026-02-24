from pydantic import BaseModel


class AddNewUserResponse(BaseModel):
    key: str
    tls_domain: str
