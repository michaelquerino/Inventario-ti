from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    full_name: str
    password: str


class CurrentUser(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
