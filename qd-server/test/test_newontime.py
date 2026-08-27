"""Tests for QD v1 newontime → QD2 schedule conversion."""

from qd_server.api.migrate import convert_newontime


def test_newontime_disabled_falls_back_to_interval():
    schedule, patch = convert_newontime({"sw": False}, old_interval=3600)
    assert schedule == {"schedule_type": "interval", "interval_seconds": 3600}
    assert patch == {}


def test_newontime_disabled_no_interval():
    schedule, patch = convert_newontime({}, old_interval=None)
    assert schedule == {"schedule_type": "once"}


def test_newontime_daily():
    schedule, patch = convert_newontime(
        {"sw": True, "time": "08:30:00", "randsw": False, "tz1": 0, "tz2": 0}
    )
    assert schedule == {"schedule_type": "daily", "run_time": "08:30:00"}
    assert patch == {}


def test_newontime_daily_with_random_window():
    schedule, patch = convert_newontime(
        {"sw": True, "time": "06:00:00", "randsw": True, "tz1": 60, "tz2": 1800}
    )
    assert schedule == {"schedule_type": "daily", "run_time": "06:01:00"}
    assert patch == {"random_delay_min": 0, "random_delay_max": 1740}


def test_newontime_negative_window_preserved():
    schedule, patch = convert_newontime(
        {"sw": True, "time": "12:00:00", "randsw": True, "tz1": -600, "tz2": 600}
    )
    assert schedule == {"schedule_type": "daily", "run_time": "11:50:00"}
    assert patch == {"random_delay_min": 0, "random_delay_max": 1200}


def test_newontime_swapped_range():
    schedule, patch = convert_newontime(
        {"sw": True, "time": "12:00:00", "randsw": True, "tz1": 900, "tz2": 300}
    )
    assert schedule == {"schedule_type": "daily", "run_time": "12:05:00"}
    assert patch == {"random_delay_min": 0, "random_delay_max": 600}


def test_newontime_crosses_midnight_and_keeps_seconds():
    schedule, patch = convert_newontime(
        {"sw": True, "time": "00:05:10", "randsw": True, "tz1": -600, "tz2": 30}
    )
    assert schedule == {"schedule_type": "daily", "run_time": "23:55:10"}
    assert patch == {"random_delay_min": 0, "random_delay_max": 630}


def test_newontime_rejects_invalid_time():
    import pytest

    with pytest.raises(ValueError, match="invalid newontime"):
        convert_newontime({"sw": True, "time": "25:90"})


def test_newontime_cron_mode():
    schedule, patch = convert_newontime(
        {
            "sw": True,
            "mode": "cron",
            "cron_val": "*/15 * * * *",
            "randsw": True,
            "tz1": "5",
            "tz2": "30",
        }
    )
    assert schedule == {
        "schedule_type": "cron",
        "cron_expression": "*/15 * * * *",
    }
    assert patch == {"random_delay_min": 5, "random_delay_max": 30}


def test_newontime_ontime_mode_is_daily_from_start_date():
    schedule, patch = convert_newontime(
        {
            "sw": True,
            "mode": "ontime",
            "date": "2026-08-25",
            "time": "00:10:10",
            "randsw": False,
        }
    )
    assert schedule == {
        "schedule_type": "daily",
        "run_time": "00:10:10",
        "start_date": "2026-08-25",
    }
    assert patch == {}


def test_legacy_ontime_schedule():
    schedule, patch = convert_newontime(
        {"sw": False},
        old_ontimeflg=True,
        old_ontime="06:22:00",
    )
    assert schedule == {
        "schedule_type": "daily",
        "run_time": "06:22:00",
    }
    assert patch == {}
