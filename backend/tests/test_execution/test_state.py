"""
tests/test_execution/test_state.py
Execution State Machine 单元测试
"""
import pytest
from app.execution.state import ExecutionState, can_transition, is_terminal


class TestExecutionState:
    """执行状态机测试"""

    def test_valid_transitions(self):
        """合法状态流转"""
        assert can_transition(ExecutionState.QUEUED, ExecutionState.RUNNING) is True
        assert can_transition(ExecutionState.RUNNING, ExecutionState.FETCHING) is True
        assert can_transition(ExecutionState.FETCHING, ExecutionState.PARSING) is True
        assert can_transition(ExecutionState.PARSING, ExecutionState.NORMALIZING) is True
        assert can_transition(ExecutionState.NORMALIZING, ExecutionState.DEDUPLICATING) is True
        assert can_transition(ExecutionState.DEDUPLICATING, ExecutionState.PERSISTING) is True
        assert can_transition(ExecutionState.PERSISTING, ExecutionState.CLUSTERING) is True
        assert can_transition(ExecutionState.CLUSTERING, ExecutionState.COMPLETED) is True

    def test_invalid_transitions(self):
        """非法状态流转"""
        assert can_transition(ExecutionState.QUEUED, ExecutionState.COMPLETED) is False
        assert can_transition(ExecutionState.COMPLETED, ExecutionState.RUNNING) is False
        assert can_transition(ExecutionState.FAILED, ExecutionState.RUNNING) is False

    def test_terminal_states(self):
        """终态判断"""
        assert is_terminal(ExecutionState.COMPLETED) is True
        assert is_terminal(ExecutionState.FAILED) is True
        assert is_terminal(ExecutionState.CANCELLED) is True
        assert is_terminal(ExecutionState.RUNNING) is False
        assert is_terminal(ExecutionState.FETCHING) is False

    def test_state_values(self):
        """状态值"""
        assert ExecutionState.QUEUED.value == "queued"
        assert ExecutionState.RUNNING.value == "running"
        assert ExecutionState.COMPLETED.value == "completed"
