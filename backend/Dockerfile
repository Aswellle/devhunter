FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    pydantic \
    pydantic-settings \
    httpx \
    beautifulsoup4 \
    chardet \
    APScheduler \
    SQLAlchemy \
    python-jose[cryptography] \
    passlib[bcrypt] \
    python-multipart

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /data

EXPOSE 8000

CMD ["python", "run.py"]
