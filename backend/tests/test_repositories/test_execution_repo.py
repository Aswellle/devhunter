"""
Tests for execution_repo recover_stale_executions fix.
Verifies the NameError bug (to_status -> to_state) is fixed.
"""
import pytest
from app.repositories.execution_repo import execution_repo
from app.repositories.task_repo import task_repo


class TestRecoverStaleExecutions:
    """Test stale execution recovery after process restart."""

    def test_recover_stale_running_executions(self, setup_test_db):
        """Test that stale running executions are marked as interrupted."""
        # Create task first (FK constraint)
        task_id = 'test-task-001'
        task_repo.insert({
            'id': task_id,
            'name': 'Test Task',
            'source_url': 'https://example.com',
            'selector_list': '.item', 'selector_title': 'h2', 'selector_link': 'a',
            'cron_expression': '0 * * * *',
            'status': 'active',
        })
        
        exec_id = 'test-exec-001'
        execution_repo.create_running(exec_id, task_id, '2026-01-01T00:00:00Z')
        
        row = execution_repo.get(exec_id)
        assert row is not None
        assert row['status'] == 'running'
        
        recovered = execution_repo.recover_stale_executions()
        assert recovered == 1
        
        row = execution_repo.get(exec_id)
        assert row['status'] == 'interrupted'
        assert 'Process restarted' in row.get('error_message', '')

    def test_recover_multiple_stale_executions(self, setup_test_db):
        """Test recovery of multiple stale executions."""
        task_id = 'test-task-002'
        task_repo.insert({
            'id': task_id,
            'name': 'Test Task 2',
            'source_url': 'https://example2.com',
            'selector_list': '.item', 'selector_title': 'h2', 'selector_link': 'a',
            'cron_expression': '0 * * * *',
            'status': 'active',
        })
        
        for i in range(3):
            execution_repo.create_running(f'exec-{i}', task_id, '2026-01-01T00:00:00Z')
        
        recovered = execution_repo.recover_stale_executions()
        assert recovered == 3

    def test_recover_no_stale_executions(self, setup_test_db):
        """Test recovery when no stale executions exist."""
        recovered = execution_repo.recover_stale_executions()
        assert recovered == 0

    def test_recover_already_finalized_execution(self, setup_test_db):
        """Test that finalized executions are not affected."""
        task_id = 'test-task-003'
        task_repo.insert({
            'id': task_id,
            'name': 'Test Task 3',
            'source_url': 'https://example3.com',
            'selector_list': '.item', 'selector_title': 'h2', 'selector_link': 'a',
            'cron_expression': '0 * * * *',
            'status': 'active',
        })
        
        exec_id = 'test-exec-finalized'
        execution_repo.create_running(exec_id, task_id, '2026-01-01T00:00:00Z')
        execution_repo.finalize(exec_id, {'status': 'success'})
        
        recovered = execution_repo.recover_stale_executions()
        assert recovered == 0
        
        row = execution_repo.get(exec_id)
        assert row['status'] == 'success'
