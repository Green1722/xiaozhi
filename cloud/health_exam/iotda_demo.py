"""Publish an IoTDA demo record, verify it, or serve it through MCP."""
import argparse
import json
import os
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from cloud.health_exam.iotda_probe import probe


SAMPLES = {"A": (175.0, 70.0), "B": (168.0, 62.0)}


def read_record(base_url, api_key, instrument, record_id):
    url = urlsplit(base_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Set a trusted HTTPS origin in HEALTH_BASE_URL")
    if not record_id.startswith("synthetic-"):
        raise ValueError("A synthetic record ID is required")
    response = httpx.get(
        base_url.rstrip("/") + "/api/exams",
        params={"instrument_id": instrument, "limit": 50},
        headers={"X-Health-API-Key": api_key},
        timeout=8,
    )
    response.raise_for_status()
    matches = [
        row for row in response.json()["records"]
        if row["source_record_id"] == record_id
        and row["instrument_id"] == instrument
        and row["source"] == "synthetic"
    ]
    if len(matches) > 1:
        raise ValueError("Multiple records matched the same synthetic ID")
    return matches[0] if matches else None


def lookup(record_id, instrument):
    return read_record(os.environ["HEALTH_BASE_URL"], os.environ["HEALTH_API_KEY"],
                       instrument, record_id)


def publish(args):
    height, weight = SAMPLES[args.sample]
    config = json.loads(args.device.read_text(encoding="utf-8-sig"))
    sent = probe(config, height_cm=height, weight_kg=weight)
    print(json.dumps(sent), flush=True)
    record_id = sent["record_id"]
    for _ in range(10):
        row = lookup(record_id, args.instrument)
        if row is not None:
            bmi = (Decimal(str(weight)) / (Decimal(str(height)) / 100) ** 2).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            if (row["height_cm"], row["weight_kg"], Decimal(str(row["bmi"]))) != (height, weight, bmi):
                raise ValueError("Forwarded values do not match the sample")
            args.selection.write_text(record_id + "\n", encoding="ascii")
            print(json.dumps(row, ensure_ascii=False))
            return
        time.sleep(1)
    raise ValueError("IoTDA acknowledged the report, but the business record was not found")


def serve(args):
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("HuaweiIoTDASyntheticExam")

    @server.tool()
    def get_last_person_height_weight() -> dict:
        """查询指定的华为云 IoTDA 模拟记录。按返回数值播报，查询失败时说明无法读取。"""
        import sys

        try:
            record_id = args.selection.read_text(encoding="utf-8-sig").strip()
            row = lookup(record_id, args.instrument)
            if row is None:
                return {"success": False, "message": "云端没有找到指定的模拟体检记录"}
            values = {name: row[name] for name in ("height_cm", "weight_kg", "bmi")}
            print("IOTDA_CLOUD_TOOL_MATCH " + json.dumps({"record_id": record_id, **values}),
                  file=sys.stderr, flush=True)
            return {"success": True, "source": "synthetic", "record_id": record_id,
                    **values, "announcement": "模拟体检记录。" + row["announcement"]}
        except (OSError, KeyError, TypeError, ValueError, httpx.HTTPError) as error:
            print("IOTDA_CLOUD_TOOL_FAILED " + type(error).__name__, file=sys.stderr, flush=True)
            return {"success": False, "message": "当前无法查询云端模拟体检数据"}

    server.run(transport="stdio")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--instrument", default="DEMO-01")
    sub = parser.add_subparsers(dest="action", required=True)
    send = sub.add_parser("publish")
    send.add_argument("--sample", choices=SAMPLES, required=True)
    send.add_argument("--device", type=Path, required=True)
    sub.add_parser("serve")
    args = parser.parse_args()
    try:
        (publish if args.action == "publish" else serve)(args)
    except (OSError, KeyError, TypeError, ValueError, httpx.HTTPError) as error:
        parser.exit(1, f"Demo failed: {type(error).__name__}\n")


if __name__ == "__main__":
    main()
