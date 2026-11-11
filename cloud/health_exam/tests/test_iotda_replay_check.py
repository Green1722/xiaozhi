"""Replay orchestration using MQTT socket stubs and the real app + SQLite.

No Internet traffic, Huawei credentials, or claim of actual cloud verification.
"""
import json
import sys
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from cloud.health_exam import iotda_probe, iotda_replay_check as replay
from cloud.health_exam.app import create_app
from cloud.health_exam.tests.test_iotda_forward import BINDINGS, FORWARD_KEY, HEADERS, READ_KEY, sample


CONFIG = {"host": "test.invalid", "device_id": "test-device", "device_secret": "test-only-secret"}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    with TestClient(create_app("sqlite:///" + (tmp_path / "check.db").as_posix(),
                               READ_KEY, BINDINGS, FORWARD_KEY)) as client:
        client.headers["X-Health-API-Key"] = READ_KEY
        state = SimpleNamespace(payloads=[], connections=0, drop_replay=False)

        class MqttSocket:
            def __init__(self):
                self.incoming = bytearray(b"\x20\x02\x00\x00\x40\x02\x00\x01")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def version(self):
                return "stub-only"

            def recv(self, count):
                data = bytes(self.incoming[:count])
                del self.incoming[:count]
                return data

            def sendall(self, data):
                if data[0] != 0x32:
                    return
                payload = json.loads(data[data.index(b'{"services":'):])
                state.payloads.append(payload)
                if state.drop_replay and len(state.payloads) == 2:
                    return
                notification = sample()
                notification["notify_data"]["body"]["services"] = payload["services"]
                response = client.post("/api/iotda/properties", headers=HEADERS, json=notification)
                assert response.status_code == 200

        def connect(*args, **kwargs):
            state.connections += 1
            return MqttSocket()

        context = SimpleNamespace(wrap_socket=lambda raw, **kwargs: raw)
        monkeypatch.setattr(iotda_probe.socket, "create_connection", connect)
        monkeypatch.setattr(iotda_probe.ssl, "create_default_context", lambda: context)
        yield client, state


def test_same_payload_after_injected_failure_has_one_unchanged_record(setup):
    client, state = setup
    evidence = replay.new_evidence()
    replay.run_check(CONFIG, client, evidence, wait_seconds=1, settle_seconds=0)
    assert state.connections == 2
    assert len(state.payloads) == 2
    assert state.payloads[0] == state.payloads[1]
    props = state.payloads[0]["services"][0]["properties"]
    assert props["height_cm"] == 175 and props["weight_kg"] == 70
    assert evidence["first_record"]["bmi"] == 22.86
    assert evidence["counts"] == {"before": 0, "after_first": 1, "after_replay": 1}
    assert evidence["unchanged_record_observed"] is True
    assert evidence["forwarding_duplicate_observed"] is None
    names = [entry["name"] for entry in evidence["events"]]
    assert names.index("injected_connection_failure_observed") < names.index("replay_puback")


def test_missing_second_forward_is_not_misrepresented_as_verified_duplicate(setup):
    client, state = setup
    state.drop_replay = True
    evidence = replay.new_evidence()
    replay.run_check(CONFIG, client, evidence, wait_seconds=1, settle_seconds=0)
    assert evidence["single_increment_observed"] is True
    assert evidence["forwarding_duplicate_observed"] is None
    assert evidence["status"] == "observations_complete_forwarding_log_confirmation_required"


def test_bad_api_key_prevents_every_mqtt_publish(setup):
    client, state = setup
    client.headers["X-Health-API-Key"] = "wrong"
    with pytest.raises(replay.CheckFailed, match="http_status_401"):
        replay.run_check(CONFIG, client, replay.new_evidence(), settle_seconds=0)
    assert state.connections == 0 and state.payloads == []


@pytest.mark.parametrize("status, body, error", [
    (502, {}, "http_status_502"),
    (200, {"status": "ok", "service": "another-service"}, "unexpected_health_service"),
])
def test_bad_health_prevents_every_mqtt_publish(setup, status, body, error):
    _, state = setup
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    with httpx.Client(base_url="https://test.invalid", transport=transport) as client:
        with pytest.raises(replay.CheckFailed, match=error):
            replay.run_check(CONFIG, client, replay.new_evidence(), settle_seconds=0)
    assert state.connections == 0 and state.payloads == []


def test_cli_failure_evidence_does_not_leak_exception_url_or_secret(tmp_path, monkeypatch, capsys):
    secret = "private-test-value-keep-out-of-evidence"
    config = tmp_path / "private.json"
    config.write_text(json.dumps(CONFIG), encoding="utf-8")
    output = tmp_path / "evidence.json"
    monkeypatch.setenv("HEALTH_BASE_URL", "https://test.invalid")
    monkeypatch.setenv("HEALTH_API_KEY", secret)
    monkeypatch.setattr(sys, "argv", ["check", "--config", str(config), "--output", str(output)])

    def failed(*args, **kwargs):
        raise httpx.ConnectError("https://test.invalid/?token=" + secret)

    monkeypatch.setattr(replay, "run_check", failed)
    assert replay.main() == 1
    saved = output.read_text(encoding="utf-8")
    assert json.loads(saved)["error_code"] == "ConnectError"
    assert secret not in saved + capsys.readouterr().out
    assert "test.invalid" not in saved


def test_cli_will_not_overwrite_device_config(tmp_path, monkeypatch):
    config = tmp_path / "private.json"
    original = json.dumps(CONFIG)
    config.write_text(original, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check", "--config", str(config), "--output", str(config)])
    assert replay.main() == 1
    assert config.read_text(encoding="utf-8") == original
