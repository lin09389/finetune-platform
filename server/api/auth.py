"""
认证 API 路由
提供用户注册、登录、刷新 Token、注销等端点
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer(auto_error=False)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


def _validate_password_strength(password: str) -> str | None:
    """验证密码强度，返回错误信息或 None"""
    if len(password) < 8:
        return "密码长度至少 8 个字符"
    if not re.search(r"[A-Z]", password):
        return "密码需包含至少一个大写字母"
    if not re.search(r"[a-z]", password):
        return "密码需包含至少一个小写字母"
    if not re.search(r"\d", password):
        return "密码需包含至少一个数字"
    return None


@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest):
    """注册新用户"""
    from security.jwt_auth import get_jwt_auth

    # 密码强度验证
    password_error = _validate_password_strength(request.password)
    if password_error:
        raise HTTPException(status_code=400, detail=password_error)

    auth = get_jwt_auth()

    # 注册用户
    user_id = auth.register_user(
        username=request.username,
        password=request.password,
    )

    if not user_id:
        raise HTTPException(status_code=409, detail="用户名已存在")

    # 自动登录，返回 Token
    token_pair = auth.create_token_pair(user_id=user_id)
    logger.info(f"新用户注册: {request.username}")

    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """用户登录"""
    from security.jwt_auth import get_jwt_auth

    auth = get_jwt_auth()

    # 验证用户名密码
    user_id = auth.authenticate(request.username, request.password)
    if not user_id:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 生成 Token 对
    token_pair = auth.create_token_pair(user_id=user_id)
    logger.info(f"用户登录: {request.username}")

    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest):
    """刷新 Access Token"""
    from security.jwt_auth import get_jwt_auth

    auth = get_jwt_auth()

    try:
        token_pair = auth.refresh_access_token(request.refresh_token)
    except Exception as e:
        logger.warning(f"Token 刷新失败: {e}")
        raise HTTPException(status_code=401, detail="无效的 Refresh Token")

    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
    )


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """注销当前 Token"""
    from security.jwt_auth import get_jwt_auth

    if not credentials:
        raise HTTPException(status_code=401, detail="未提供 Token")

    auth = get_jwt_auth()
    auth.logout(credentials.credentials)

    return {"message": "已注销"}


@router.get("/me")
async def get_current_user_info(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """获取当前用户信息"""
    from security.jwt_auth import get_jwt_auth

    if not credentials:
        raise HTTPException(status_code=401, detail="未提供 Token")

    auth = get_jwt_auth()

    try:
        payload = auth.verify_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    user_info = auth.get_user_info(payload.user_id)
    if not user_info:
        raise HTTPException(status_code=404, detail="用户不存在")

    return user_info
