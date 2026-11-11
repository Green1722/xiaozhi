"""Explicit synthetic IoTDA replay check; never claims device-side recovery.

Run from the repository root with HEALTH_BASE_URL / HEALTH_API_KEY configured.
The connection error is deliberately injected into this test process only.
Two PUBACKs and one database row do not prove that both forwards arrived: obtain
corresponding cloud forwarding/application logs separately.
"""
import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx

from cloud.health_exam import iotda_probe


class CheckFailed(Exception):
    """Fixed, non-secret diagnostic suitable for the evidence file."""


class InjectedConnectionFailure(OSError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_evidence():
    return {
        "schema_version": 1,
        "started_at_utc": utc_now(),
        "status": "running",
        "scope": "computer synthetic MQTT probe with injected connection failure",
        "forwarding_duplicate_observed": None,
        "forwarding_duplicate_note": "Not verified; correlate both publishes with cloud forwarding/application logs.",
        "device_offline_cache_verified": False,
        "device_auto_reconnect_verified": False,
        "playback_verified": False,
        "events": [],
    }


def event(evidence, name, **values):
    evidence["events"].append({"name": name, "at_utc": utc_now(), **values})


def check_response(response):
    if response.status_code != 200:
        # Never include response text, URL, request headers, or exception str().
        raise CheckFailed("http_status_" + str(response.status_code))
    return response.json()


def total_count(client, instrument):
    data = check_response(client.get("/api/exams", params={"instrument_id": instrument, "limit": 1}))
    count = data.get("total_count")
    if type(count) is not int or count < 0:
        raise CheckFailed("invalid_total_count")
    return count


def exact_record(client, record_key, wait_seconds):
    deadline = time.monotonic() + wait_seconds
    while True:
        response = client.get("/api/exams/" + record_key)
        if response.status_code == 200:
            return response.json()
        if response.status_code != 404:
            check_response(response)
        if time.monotonic() >= deadline:
            raise CheckFailed("published_record_not_found")
        time.sleep(min(1, max(0, deadline - time.monotonic())))


def validate_record(row, instrument, record_id, measured_at, key):
    expected = {"id": key, "instrument_id": instrument, "source_record_id": record_id,
                "source": "synthetic", "height_cm": 175.0, "weight_kg": 70.0, "bmi": 22.86,
                "measured_at": measured_at}
    if any(row.get(name) != value for name, value in expected.items()):
        raise CheckFailed("business_record_mismatch")
    if not isinstance(row.get("received_at"), str):
        raise CheckFailed("missing_received_at")
    # Only synthetic measurement fields are included, never arbitrary responses.
    return dict(expected, received_at=row["received_at"])


def check_publish(result, record_id):
    if (not all(result.get(name) is True for name in
                ("tls_verified", "mqtt_authenticated", "puback_received"))
            or result.get("record_id") != record_id):
        raise CheckFailed("publish_not_acknowledged")


def run_check(config, client, evidence, *, instrument="DEMO-01", wait_seconds=30, settle_seconds=5):
    health = check_response(client.get("/healthz"))
    if health != {"status": "ok", "service": "xiaozhi-health-exam"}:
        raise CheckFailed("unexpected_health_service")
    before = total_count(client, instrument)
    event(evidence, "preflight_passed", initial_total_count=before)

    measured = datetime.now(timezone.utc)
    measured_at = measured.isoformat().replace("+00:00", "Z")
    record_id = "synthetic-" + measured.strftime("%Y%m%dT%H%M%S%fZ")
    key = hashlib.sha256(f"{instrument}\0{record_id}".encode()).hexdigest()
    evidence.update(record_id=record_id, instrument_id=instrument, business_record_key=key)
    # Verify the ID is new before publishing; 401/other failures also stop here.
    if client.get("/api/exams/" + key).status_code != 404:
        raise CheckFailed("new_record_precondition_failed")

    class MeasurementClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return measured.astimezone(tz) if tz else measured.replace(tzinfo=None)

    with patch.object(iotda_probe, "datetime", MeasurementClock):
        event(evidence, "first_publish_started")
        first = iotda_probe.probe(config)
        check_publish(first, record_id)
        event(evidence, "first_puback", tls_verified=True, mqtt_authenticated=True)
        row = exact_record(client, key, wait_seconds)
        original = validate_record(row, instrument, record_id, measured_at, key)
        after_first = total_count(client, instrument)
        evidence["first_record"] = original
        event(evidence, "first_record_observed", total_count=after_first)

        event(evidence, "injected_connection_failure_started")
        with patch.object(iotda_probe.socket, "create_connection",
                          side_effect=InjectedConnectionFailure) as connect:
            try:
                iotda_probe.probe(config)
            except InjectedConnectionFailure:
                if connect.call_count != 1:
                    raise CheckFailed("unexpected_connection_attempt_count") from None
            else:
                raise CheckFailed("injected_failure_not_observed")
        event(evidence, "injected_connection_failure_observed", attempted_connections=1)

        event(evidence, "replay_publish_started")
        replay = iotda_probe.probe(config)
        check_publish(replay, record_id)
        event(evidence, "replay_puback", tls_verified=True, mqtt_authenticated=True)

    # Existing data can be returned before the second forward arrives. This
    # bounded observation does not turn that uncertainty into a delivery claim.
    time.sleep(settle_seconds)
    current = validate_record(exact_record(client, key, wait_seconds),
                              instrument, record_id, measured_at, key)
    after_replay = total_count(client, instrument)
    if original != current:
        raise CheckFailed("original_business_record_changed")
    evidence["counts"] = {"before": before, "after_first": after_first, "after_replay": after_replay}
    evidence["single_increment_observed"] = after_first == before + 1 == after_replay
    evidence["unchanged_record_observed"] = True
    event(evidence, "replay_observation_finished", settle_seconds=settle_seconds)
    if not evidence["single_increment_observed"]:
        raise CheckFailed("instrument_count_changed_unexpectedly")
    evidence["status"] = "observations_complete_forwarding_log_confirmation_required"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--instrument", default="DEMO-01")
    parser.add_argument("--wait-seconds", type=int, default=30, choices=range(1, 61), metavar="1..60")
    parser.add_argument("--settle-seconds", type=int, default=5, choices=range(0, 31), metavar="0..30")
    args = parser.parse_args()
    evidence = new_evidence()
    output_ready = False
    try:
        # Refuse to overwrite earlier evidence or a mistakenly selected config.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as destination:
            destination.write(json.dumps(evidence, ensure_ascii=False, indent=2))
        output_ready = True
        origin = os.environ["HEALTH_BASE_URL"].rstrip("/")
        url = urlsplit(origin)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.path or url.query or url.fragment):
            raise CheckFailed("invalid_https_origin")
        api_key = os.environ["HEALTH_API_KEY"]
        if len(api_key) < 24 or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", args.instrument):
            raise CheckFailed("invalid_private_configuration")
        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        with httpx.Client(base_url=origin, headers={"X-Health-API-Key": api_key},
                          timeout=8, follow_redirects=False) as client:
            run_check(config, client, evidence, instrument=args.instrument,
                      wait_seconds=args.wait_seconds, settle_seconds=args.settle_seconds)
    except Exception as error:
        evidence["status"] = "failed"
        evidence["error_code"] = str(error) if isinstance(error, CheckFailed) else type(error).__name__
    evidence["finished_at_utc"] = utc_now()
    if not output_ready:
        print("Evidence output must be a new writable file; nothing was published.")
        return 1
    try:
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        print("Evidence output could not be written.")
        return 1
    print(json.dumps({"status": evidence["status"],
                      "error_code": evidence.get("error_code"),
                      "forwarding_duplicate_observed": None}))
    return int(evidence["status"] == "failed")


if __name__ == "__main__":
    raise SystemExit(main())
