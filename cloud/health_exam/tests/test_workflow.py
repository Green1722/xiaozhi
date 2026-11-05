import ast
import json
import logging
import urllib.request
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from cloud.health_exam.app import create_app

KEY = "test-only-key-not-a-production-secret"
HEADERS = {"X-API-Key": KEY}
PAYLOAD = {"id": "measurement-001", "instrument_id": "DEMO-01", "height_cm": 175,
           "weight_kg": 70, "timestamp": "2026-11-04 10:00:00", "source": "synthetic"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'exams.db'}", KEY)) as client:
        yield client


def ingest(client, **kwargs):
    return client.post("/api/exams", headers=HEADERS, json={**PAYLOAD, **kwargs})


def test_authentication_blocks_read_and_write(client):
    assert client.get("/api/exams").status_code == 401
    assert client.post("/api/exams", json=PAYLOAD).status_code == 401
    assert client.get("/api/exams", headers={"X-API-Key": "wrong"}).status_code == 401


def test_dedicated_health_header_for_proxy(client):
    headers = {"X-Health-API-Key": KEY}
    assert client.post("/api/exams", headers=headers, json=PAYLOAD).status_code == 200
    assert client.get("/api/exams", headers=headers).json()["total_count"] == 1
    assert client.get("/api/exams", headers={"X-Health-API-Key": "wrong"}).status_code == 401
    # Explicit dedicated credentials take precedence; no fallback on a bad value.
    assert client.get("/api/exams", headers={**HEADERS, "X-Health-API-Key": "wrong"}).status_code == 401


def test_known_bmi_and_legacy_fields_not_trusted(client):
    # Independent reference: 70 / (1.75**2) = 22.857142..., rounded to 22.86.
    response = ingest(client, bmi=99, advice="untrusted", patient_name="not stored")
    assert response.status_code == 200
    record = response.json()["record"]
    assert record["bmi"] == 22.86
    assert record["measured_at"] == "2026-11-04T02:00:00Z"
    assert record["speech_status"] == "unconfirmed"
    assert record["source"] == "synthetic"
    assert "untrusted" not in str(record)
    assert "patient_name" not in record


@pytest.mark.parametrize("field,value", [("height_cm", 0), ("weight_kg", -1),
                                         ("height_cm", "NaN"), ("weight_kg", "Infinity")])
def test_invalid_measurements_rejected(client, field, value):
    assert ingest(client, **{field: value}).status_code == 422
    assert client.get("/api/exams", headers=HEADERS).json()["records"] == []


def test_retry_is_idempotent_but_conflicting_data_fails(client):
    first = ingest(client).json()
    retry = ingest(client)
    assert retry.status_code == 200 and retry.json()["duplicate"]
    assert retry.json()["record"]["id"] == first["record"]["id"]
    assert ingest(client, weight_kg=71).status_code == 409
    assert len(client.get("/api/exams", headers=HEADERS).json()["records"]) == 1


def test_same_source_id_on_two_instruments_is_not_deduplicated(client):
    first = ingest(client).json()["record"]
    second = ingest(client, instrument_id="DEMO-02").json()["record"]
    assert first["id"] != second["id"]
    rows = client.get("/api/exams?instrument_id=DEMO-02", headers=HEADERS).json()["records"]
    assert len(rows) == 1 and rows[0]["instrument_id"] == "DEMO-02"


def test_restart_retains_record(tmp_path):
    url = f"sqlite:///{tmp_path / 'restart.db'}"
    with TestClient(create_app(url, KEY)) as first:
        record = ingest(first).json()["record"]
    with TestClient(create_app(url, KEY)) as second:
        saved = second.get(f"/api/exams/{record['id']}", headers=HEADERS)
        assert saved.status_code == 200
        assert saved.json()["source_record_id"] == PAYLOAD["id"]


def test_explicit_playback_events_and_no_false_confirmation(client):
    record_id = ingest(client).json()["record"]["id"]
    route = f"/api/exams/{record_id}/speech-events"
    event = {"event_id": "request-1", "status": "requested"}
    assert client.post(route, headers=HEADERS, json=event).json()["speech_status"] == "requested"
    event = {"event_id": "ack-1", "status": "device_confirmed"}
    assert client.post(route, headers=HEADERS, json=event).json()["speech_status"] == "device_confirmed"
    assert client.post(route, headers=HEADERS, json=event).status_code == 200
    assert client.post(route, headers=HEADERS, json={"event_id": "late-1", "status": "failed"}).status_code == 409


def test_missing_maas_not_fabricated(client, monkeypatch):
    monkeypatch.delenv("MAAS_API_KEY", raising=False)
    record_id = ingest(client).json()["record"]["id"]
    assert client.post(f"/api/exams/{record_id}/explanation", headers=HEADERS).status_code == 503


def test_maas_adapter_contract_without_external_call(client, monkeypatch):
    monkeypatch.setenv("MAAS_CHAT_URL", "https://example.invalid/openai/v1/chat/completions")
    monkeypatch.setenv("MAAS_MODEL", "test-model")
    monkeypatch.setenv("MAAS_API_KEY", "test-only")
    calls = []

    async def fake_post(self, url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "模拟模型响应，仅用于接口测试"}}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    record_id = ingest(client).json()["record"]["id"]
    result = client.post(f"/api/exams/{record_id}/explanation", headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["kind"] == "ai_generated_explanation"
    assert calls[0]["model"] == "test-model" and calls[0]["stream"] is False
    assert "DEMO-01" not in str(calls[0]["messages"])


def test_actual_legacy_upload_function_feeds_cloud(client, monkeypatch):
    # Extract the real function to avoid starting MQTT or loading MCP on import.
    repo = Path(__file__).resolve().parents[3]
    source = repo / "小智/hight_weight/zhudong_mcp/physical_exam_control.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "upload_exam_data")

    class Reply:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass

    def urlopen(req, timeout):
        data = json.loads(req.data)
        result = client.post("/api/exams", headers={"X-API-Key": req.get_header("X-api-key")}, json=data)
        assert result.status_code == 200
        return Reply()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    namespace = {"Dict": dict, "Any": object, "UPLOAD_ENABLED": True, "UPLOAD_URL": "https://example.invalid/api/exams",
                 "UPLOAD_API_KEY": KEY, "json": json, "urllib": urllib, "logger": logging.getLogger("test")}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    assert namespace["upload_exam_data"](PAYLOAD)
    rows = client.get("/api/exams", headers=HEADERS).json()["records"]
    assert len(rows) == 1 and rows[0]["bmi"] == 22.86


def test_page_and_health_available_without_measurement_data(client):
    assert client.get("/healthz").json()["status"] == "ok"
    html = client.get("/")
    assert html.status_code == 200 and "小智体检记录" in html.text


def test_weak_key_rejected(tmp_path):
    with pytest.raises(RuntimeError, match="HEALTH_API_KEY"):
        create_app(f"sqlite:///{tmp_path / 'weak.db'}", "short")


def test_real_cloud_query_helper_can_feed_legacy_latest_query(client, monkeypatch):
    ingest(client)
    repo = Path(__file__).resolve().parents[3]
    source = repo / "小智/hight_weight/zhudong_mcp/physical_exam_control.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "get_cloud_exam_records")

    class Reply:
        def __init__(self, data): self.data = json.dumps(data).encode()
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return self.data

    def urlopen(req, timeout):
        path = req.full_url.removeprefix("https://example.invalid")
        result = client.get(path, headers={"X-API-Key": req.get_header("X-api-key")})
        assert result.status_code == 200
        return Reply(result.json())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    namespace = {"UPLOAD_URL": "https://example.invalid/api/exams", "UPLOAD_API_KEY": KEY,
                 "json": json, "urllib": urllib}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    result = namespace["get_cloud_exam_records"](1, "DEMO-01")
    assert result["source"] == "cloud" and result["total_count"] == 1
    assert result["records"][0]["id"] == PAYLOAD["id"]
    assert result["records"][0]["timestamp"] == "2026-11-04T02:00:00Z"


def test_cloud_query_failure_is_not_reported_as_no_records(monkeypatch):
    repo = Path(__file__).resolve().parents[3]
    source = repo / "小智/hight_weight/zhudong_mcp/physical_exam_control.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "get_exam_records")
    function.decorator_list = []

    def unavailable(*args): raise OSError("offline")

    namespace = {"UPLOAD_ENABLED": True, "UPLOAD_URL": "https://example.invalid/api/exams",
                 "get_cloud_exam_records": unavailable, "logger": logging.getLogger("test")}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    result = namespace["get_exam_records"]()
    assert result["success"] is False and "error" in result
    assert "records" not in result
