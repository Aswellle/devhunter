"""
app/core/rate_limit.py
共享的 slowapi Limiter 单例。
必须全局唯一：main.py 的 app.state.limiter 与各路由的 @limiter.limit(...)
装饰器必须引用同一个实例，否则限流状态不会生效。
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
