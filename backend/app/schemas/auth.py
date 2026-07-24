"""
app/schemas/auth.py
认证相关 Pydantic 模型
"""
from pydantic import BaseModel


class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
