"""
app/schemas/execution.py
任务执行记录 Pydantic 模型
"""
from pydantic import BaseModel


class ExecutionResponse(BaseModel):
    id: str
    task_id: str
    status: str          # success | failure | warning
    items_fetched: int
    items_new: int
    duration_ms: int
    error_message: str | None
    executed_at: str

    model_config = {"from_attributes": True}
