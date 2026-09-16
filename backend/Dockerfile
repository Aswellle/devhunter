FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# S8: 从 requirements.txt 安装锁定版本，而非裸包名——避免上游破坏性
# 发布或供应链投毒在未经审查的情况下静默影响生产构建。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /data

# S7: 非 root 用户运行。默认以 UID 0 运行会在容器被攻破时把爆炸半径
# 放大到整个容器文件系统；appuser 只能写自己需要的 /app、/data。
RUN useradd --create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

CMD ["python", "run.py"]
