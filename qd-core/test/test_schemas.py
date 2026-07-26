"""Tests for QD Core schemas."""

import pytest
from qd_core.schemas.har import HARRequest, HARResponse, HARTemplate, HTTPMethod
from qd_core.schemas.task import ScheduleConfig, ScheduleType, TaskStatus


def test_har_request_creation():
    """Test creating a HAR request."""
    req = HARRequest(
        method=HTTPMethod.GET,
        url="https://example.com/api/test",
        headers=[{"name": "Accept", "value": "application/json"}],
    )
    assert req.method == HTTPMethod.GET
    assert req.url == "https://example.com/api/test"


def test_har_template_creation():
    """Test creating a HAR template."""
    template = HARTemplate(
        name="Test Template",
        description="A test template",
        requests=[
            HARRequest(method=HTTPMethod.GET, url="https://example.com"),
        ],
        variables={"token": "abc123"},
    )
    assert template.name == "Test Template"
    assert len(template.requests) == 1
    assert template.variables["token"] == "abc123"


def test_har_template_defaults():
    """Test template default values."""
    template = HARTemplate(name="Test")
    assert template.version == "1.0"
    assert template.enabled is True
    assert template.requests == []
    assert template.variables == {}


def test_schedule_config_interval():
    """Test interval-based schedule config."""
    config = ScheduleConfig(
        schedule_type=ScheduleType.INTERVAL,
        interval_seconds=300,
    )
    assert config.schedule_type == ScheduleType.INTERVAL
    assert config.interval_seconds == 300


def test_task_status():
    """Test task status enum."""
    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.RUNNING == "running"
    assert TaskStatus.SUCCESS == "success"
