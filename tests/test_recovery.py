"""Recovery 恢复管理器测�?""

import pytest
from openspider.core.recovery import RecoveryManager


def test_calculate_backoff_basic():
    """基础退避计�?""
    assert RecoveryManager.calculate_backoff(0, 60) == 60
    assert RecoveryManager.calculate_backoff(1, 60) == 120
    assert RecoveryManager.calculate_backoff(2, 60) == 240


def test_calculate_backoff_max():
    """退避上�?1 小时"""
    result = RecoveryManager.calculate_backoff(100, 60)
    assert result == RecoveryManager.MAX_BACKOFF


def test_calculate_backoff_exponential():
    """指数退�?""
    delay = 10
    assert RecoveryManager.calculate_backoff(0, delay) == 10
    assert RecoveryManager.calculate_backoff(1, delay) == 20
    assert RecoveryManager.calculate_backoff(2, delay) == 40
    assert RecoveryManager.calculate_backoff(3, delay) == 80


