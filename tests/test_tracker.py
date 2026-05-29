"""Tests for the job tracker module."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.models import Job
from src.core import tracker


def _make_job(title: str, company: str, url: str, board: str = "test") -> Job:
    return Job(id=url, title=title, company=company, url=url, board=board)


def test_filter_new_all_new(tmp_path):
    data_file = tmp_path / "seen_jobs.json"
    data_file.write_text("{}")
    with patch.object(tracker, "DATA_FILE", data_file):
        jobs = [_make_job("UX Designer", "Acme", "https://example.com/1")]
        new = tracker.filter_new(jobs)
    assert len(new) == 1


def test_filter_new_already_seen(tmp_path):
    job = _make_job("UX Designer", "Acme", "https://example.com/1")
    key = tracker._job_key(job)
    data_file = tmp_path / "seen_jobs.json"
    data_file.write_text(json.dumps({key: {"seen_at": "2099-01-01T00:00:00", "url": job.url, "board": "test", "title": "x", "company": "x"}}))
    with patch.object(tracker, "DATA_FILE", data_file):
        new = tracker.filter_new([job])
    assert len(new) == 0


def test_mark_seen(tmp_path):
    data_file = tmp_path / "seen_jobs.json"
    data_file.write_text("{}")
    job = _make_job("Product Designer", "Corp", "https://example.com/2")
    with patch.object(tracker, "DATA_FILE", data_file):
        tracker.mark_seen([job])
        seen = tracker.load_seen()
    key = tracker._job_key(job)
    assert key in seen
    assert seen[key]["company"] == "Corp"
