"""Read the exact verified S200 measurement from the Huawei exam API."""
from decimal import Decimal, ROUND_HALF_UP
import json
import sys

import httpx
from mcp.server.fastmcp import FastMCP
from exam_guidance import lifestyle_guidance
from s200_config import PRIVATE, api_headers, cloud_url
mcp = FastMCP("HuaweiIoTDAMeasuredExam")


@mcp.tool()
def get_last_person_height_weight(confirmed_adult: bool = False) -> dict:
    """查询本次实测并播报数值和返回的生活建议。仅在测试者明确确认已满18岁且适用普通成人参考范围时传 true；年龄未知时保持 false。若查询失败，直接说明原因。"""
    try:
        expected = json.loads((PRIVATE / "iotda-measured-cloud-result.private.json").read_text(encoding="utf-8"))
        response = httpx.get(
            cloud_url() + "/api/exams/" + expected["id"],
            headers=api_headers(),
            timeout=8,
        )
        response.raise_for_status()
        record = response.json()
        fields = ("id", "source_record_id", "instrument_id", "height_cm", "weight_kg", "measured_at")
        height = Decimal(str(record["height_cm"])) / 100
        bmi = (Decimal(str(record["weight_kg"])) / height ** 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if (record["source"] != "measured"
                or any(record[k] != expected[k] for k in fields) or bmi != Decimal(str(record["bmi"]))):
            raise ValueError("Unexpected cloud measurement")
        print("IOTDA_MEASURED_TOOL_MATCH", file=sys.stderr, flush=True)
        return {"success": True, "source": "measured", "height_cm": record["height_cm"],
                "weight_kg": record["weight_kg"], "bmi": record["bmi"],
                "announcement": record["announcement"],
                "guidance": lifestyle_guidance(bmi, confirmed_adult)}
    except (ArithmeticError, OSError, KeyError, ValueError, httpx.HTTPError) as error:
        print("IOTDA_MEASURED_TOOL_FAILED " + type(error).__name__, file=sys.stderr, flush=True)
        return {"success": False, "message": "当前无法查询本次云端实测体检数据"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
