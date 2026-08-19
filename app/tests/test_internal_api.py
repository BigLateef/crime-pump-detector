"""
Tests app.api.internal's _require_scan_secret directly — pure logic, no
Redis/DB needed. The lock/status behavior itself (acquire_lock,
release_lock, record_success/failure) needs a real Redis and is not
covered here — see the "not executed" list in this phase's final report.
"""
import pytest
from fastapi import HTTPException

from app.api.internal import _require_scan_secret
from app.core.config import get_settings


def test_correct_secret_passes():
    settings = get_settings()
    _require_scan_secret(settings.scan_trigger_secret)  # should not raise


def test_wrong_secret_rejected():
    with pytest.raises(HTTPException) as exc_info:
        _require_scan_secret("definitely-wrong")
    assert exc_info.value.status_code == 401


def test_missing_secret_rejected():
    with pytest.raises(HTTPException) as exc_info:
        _require_scan_secret(None)
    assert exc_info.value.status_code == 401


def test_empty_string_secret_rejected():
    with pytest.raises(HTTPException) as exc_info:
        _require_scan_secret("")
    assert exc_info.value.status_code == 401


def test_wrong_and_missing_secret_give_identical_error_message():
    with pytest.raises(HTTPException) as exc_missing:
        _require_scan_secret(None)
    with pytest.raises(HTTPException) as exc_wrong:
        _require_scan_secret("wrong-value")
    assert exc_missing.value.detail == exc_wrong.value.detail
    assert exc_missing.value.status_code == exc_wrong.value.status_code
