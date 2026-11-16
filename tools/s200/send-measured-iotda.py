"""Send the locally validated S200 record after cloud setup is confirmed."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import sys
import time

import httpx

from s200_config import PRIVATE, ROOT, api_headers, cloud_url

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cloud.health_exam.iotda_probe import mqtt_string, packet, password, read_packet
from exam_guidance import lifestyle_guidance


def capture_measurement(height):
    print("Waiting for an authenticated S200 measurement", flush=True)
    result = subprocess.run(
        [sys.executable, str(HERE / "scan-s200.py"), "--coded", "--capture-json"],
        cwd=HERE, capture_output=True, text=True, timeout=70,
    )
    if result.returncode:
        raise RuntimeError("S200 capture failed or timed out")
    reading = json.loads(result.stdout.splitlines()[-1])
    measured_at = reading["received_at_utc"]
    return {
        "record_id": "s200-" + datetime.fromisoformat(measured_at).strftime("%Y%m%dT%H%M%S%fZ"),
        "height_cm": float(height),
        "weight_kg": reading["weight_kg"],
        "measured_at": measured_at,
    }


def push_announcement(client, url, row, confirmed_adult, receipt_dir):
    text = "测量完成。" + row["announcement"] + lifestyle_guidance(
        Decimal(str(row["bmi"])), confirmed_adult
    )
    receipt_dir.mkdir(exist_ok=True)
    receipt_path = receipt_dir / (row["id"] + ".json")
    try:
        with receipt_path.open("x", encoding="utf-8") as receipt:
            json.dump({"status": "attempted"}, receipt)
    except FileExistsError:
        print("Proactive request already attempted for this measurement", flush=True)
        return
    # An ambiguous timeout may already have played audio. Do not automatically retry.
    response = client.post(url, json={"text": text})
    response.raise_for_status()
    receipt_path.write_text('{"status":"accepted"}', encoding="utf-8")
    print("Proactive request accepted; device playback is unconfirmed", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--announce", action="store_true",
                        help="Request proactive speech after the measurement is verified in Huawei Cloud")
    parser.add_argument("--confirmed-adult", action="store_true",
                        help="Use adult BMI reference after confirming it applies to this tester")
    parser.add_argument("--height-cm", type=Decimal,
                        help="Use this measured height and wait for a fresh S200 reading")
    args = parser.parse_args()
    if args.announce and not args.publish:
        parser.error("--announce requires --publish")
    if args.height_cm is not None and (
        not args.publish or not args.height_cm.is_finite() or not 0 < args.height_cm <= 500
        or args.height_cm != args.height_cm.quantize(Decimal("0.01"))
    ):
        parser.error("--height-cm requires --publish and a height between 0 and 500 cm with up to two decimal places")
    push_url = os.environ.get("XIAOZHI_TTS_PUSH_URL", "").strip()
    if args.announce:
        url = httpx.URL(push_url)
        if url.scheme != "https" or not url.host:
            parser.error("--announce requires an HTTPS XIAOZHI_TTS_PUSH_URL for the target device")
    device = json.loads((PRIVATE / "iotda-measured-device.private.json").read_text(encoding="utf-8-sig"))
    dev = device["device_id"]
    binding = json.loads((PRIVATE / "iotda-measured-binding.json").read_text(encoding="utf-8-sig"))[dev]
    if binding["source"] != "measured" or not binding["instrument_id"]:
        raise ValueError("Unexpected device binding")
    base_url = cloud_url() if args.publish else None
    headers = api_headers() if args.publish else None
    props = (capture_measurement(args.height_cm) if args.height_cm is not None else
             json.loads((PRIVATE / "iotda-measured-pending.private.json").read_text(encoding="utf-8-sig")))
    if not args.publish:
        print("Local measured record and independent device config loaded")
        return
    path = "/api/exams/" + sha256(
        (binding["instrument_id"] + "\0" + props["record_id"]).encode()
    ).hexdigest()
    with httpx.Client(base_url=base_url,
                      timeout=8, follow_redirects=False) as client:
        health = client.get("/healthz")
        if health.status_code != 200 or health.json().get("service") != "xiaozhi-health-exam":
            raise RuntimeError("Cloud service health preflight failed")
        if client.get(path, headers=headers).status_code not in (200, 404):
            raise RuntimeError("Cloud query preflight failed")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        body = (mqtt_string("MQTT") + bytes([4, 0xC2]) + struct.pack("!H", 30)
                + mqtt_string(f"{dev}_0_1_{stamp}") + mqtt_string(dev)
                + mqtt_string(password(device["device_secret"], stamp)))
        host = device["host"]
        topic = f"$oc/devices/{dev}/sys/properties/report"
        payload = {"services": [{"service_id": "PhysicalExam", "properties": props}]}
        with socket.create_connection((host, device["port"]), timeout=12) as raw:
            with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as conn:
                conn.sendall(packet(0x10, body))
                if read_packet(conn) != (0x20, b"\0\0"):
                    raise RuntimeError("IoTDA authentication rejected")
                conn.sendall(packet(0x32, mqtt_string(topic) + b"\0\1" + json.dumps(payload).encode()))
                for _ in range(10):
                    if read_packet(conn) == (0x40, b"\0\1"):
                        conn.sendall(b"\xe0\0")
                        break
                else:
                    raise RuntimeError("Matching PUBACK not received")
        print("IoTDA PUBACK received", flush=True)
        for _ in range(20):
            response = client.get(path, headers=headers)
            if response.status_code == 404:
                time.sleep(1)
                continue
            response.raise_for_status()
            row = response.json()
            if (row["source"] != "measured" or row["instrument_id"] != binding["instrument_id"]
                    or row["id"] != path.rsplit("/", 1)[-1]
                    or row["source_record_id"] != props["record_id"]
                    or datetime.fromisoformat(row["measured_at"]) != datetime.fromisoformat(props["measured_at"])
                    or any(row[k] != props[k] for k in ("height_cm", "weight_kg"))):
                raise RuntimeError("Cloud record differs from the pending measurement")
            (PRIVATE / "iotda-measured-cloud-result.private.json").write_text(
                json.dumps(row, ensure_ascii=False), encoding="utf-8")
            print("Cloud measured record verified")
            if args.announce:
                push_announcement(client, push_url, row, args.confirmed_adult, PRIVATE / "speech-receipts")
            return
        raise RuntimeError("No matching business record after PUBACK")


if __name__ == "__main__":
    try:
        main()
    except (ArithmeticError, OSError, ValueError, KeyError, RuntimeError, httpx.HTTPError,
            subprocess.TimeoutExpired) as error:
        sys.exit(f"Measured record check failed ({type(error).__name__})")
