"""
app/execution/state.py
Execution State Machine：任务执行状态机。

状态流转：
queued → running → fetching → parsing → normalizing → deduplicating → persisting → clustering → completed
                                                                                    ↓
                                                                              partial_failed
                                                                                    ↓
                                                                                  failed
                                                                                    ↓
                                                                                cancelled
"""
from enum import Enum
from typing import Any


class ExecutionState(str, Enum):
    """执行状态枚举"""
    QUEUED = "queued"
    RUNNING = "running"
    FETCHING = "fetching"
    PARSING = "parsing"
    NORMALIZING = "normalizing"
    DEDUPLICATING = "deduplicating"
    PERSISTING = "persisting"
    CLUSTERING = "clustering"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# 合法状态流转
VALID_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.QUEUED: {
        ExecutionState.RUNNING,
        ExecutionState.CANCELLED,
    },
    ExecutionState.RUNNING: {
        ExecutionState.FETCHING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.FETCHING: {
        ExecutionState.PARSING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.PARSING: {
        ExecutionState.NORMALIZING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.NORMALIZING: {
        ExecutionState.DEDUPLICATING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.DEDUPLICATING: {
        ExecutionState.PERSISTING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.PERSISTING: {
        ExecutionState.CLUSTERING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.CLUSTERING: {
        ExecutionState.COMPLETED,
        ExecutionState.PARTIAL_FAILED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.COMPLETED: set(),  # 终态
    ExecutionState.PARTIAL_FAILED: set(),  # 终态
    ExecutionState.FAILED: set(),  # 终态
    ExecutionState.CANCELLED: set(),  # 终态
}


def can_transition(from_state: ExecutionState, to_state: ExecutionState) -> bool:
    """检查状态流转是否合法"""
    return to_state in VALID_TRANSITIONS.get(from_state, set())


def is_terminal(state: ExecutionState) -> bool:
    """是否为终态"""
    return state in {
        ExecutionState.COMPLETED,
        ExecutionState.PARTIAL_FAILED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    }


def get_event_type_for_state(state: ExecutionState) -> str:
    """获取状态对应的事件类型"""
    return state.value
