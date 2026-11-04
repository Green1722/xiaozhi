from __future__ import annotations

import hashlib
import hmac
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, Numeric, String, UniqueConstraint, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

UTC = timezone.utc
SHANGHAI = timezone(timedelta(hours=8))
HERE = Path(__file__).parent


class Base(DeclarativeBase):
    pass


class Exam(Base):
    __tablename__ = "physical_exams"
    __table_args__ = (UniqueConstraint("instrument_id", "source_record_id"), {"mysql_collate": "utf8mb4_bin"})
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_record_id: Mapped[str] = mapped_column(String(96))
    instrument_id: Mapped[str] = mapped_column(String(64), index=True)
    height_cm: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    bmi: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    measured_at: Mapped[datetime] = mapped_column(DateTime)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(24))
    speech_status: Mapped[str] = mapped_column(String(24), default="unconfirmed")
    speech_event_id: Mapped[str | None] = mapped_column(String(96), nullable=True)


class ExamInput(BaseModel):
    # Existing bridge fields bmi/advice are deliberately not trusted or stored.
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9_.:-]+$")
    instrument_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    # Application input bounds, NOT instrument range or medical thresholds.
    height_cm: Decimal = Field(gt=0, le=500, max_digits=6, decimal_places=2)
    weight_kg: Decimal = Field(gt=0, le=1000, max_digits=6, decimal_places=2)
    timestamp: datetime
    source: Literal["measured", "synthetic"] = "measured"

    @field_validator("timestamp")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        # Legacy bridge uses a naive China-local timestamp.
        if value.tzinfo is None:
            value = value.replace(tzinfo=SHANGHAI)
        return value.astimezone(UTC).replace(tzinfo=None)


class SpeechEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=96)
    status: Literal["requested", "device_confirmed", "failed"]


def calculate_bmi(height_cm: Decimal, weight_kg: Decimal) -> Decimal:
    meters = height_cm / Decimal("100")
    return (weight_kg / (meters * meters)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def serialize(row: Exam) -> dict:
    return {
        "id": row.id,
        "source_record_id": row.source_record_id,
        "instrument_id": row.instrument_id,
        "height_cm": float(row.height_cm),
        "weight_kg": float(row.weight_kg),
        "bmi": float(row.bmi),
        "measured_at": row.measured_at.isoformat() + "Z",
        "received_at": row.received_at.isoformat() + "Z",
        "source": row.source,
        "speech_status": row.speech_status,
        "announcement": f"本次测量身高{row.height_cm}厘米，体重{row.weight_kg}公斤，BMI为{row.bmi}。",
    }


def create_app(database_url: str | None = None, api_key: str | None = None) -> FastAPI:
    database_url = database_url or os.environ.get("DATABASE_URL", "sqlite:///./data/exams.db")
    api_key = api_key or os.environ.get("HEALTH_API_KEY", "")
    if len(api_key) < 24 or api_key == "REPLACE_ME":
        raise RuntimeError("Set HEALTH_API_KEY to a private random value of at least 24 characters")
    if database_url.startswith("sqlite:///./"):
        Path(database_url.removeprefix("sqlite:///./")).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {}
    if database_url.startswith("sqlite:"):
        connect_args["check_same_thread"] = False
    elif database_url.startswith("mysql+pymysql:") and os.environ.get("RDS_SSL_CA"):
        connect_args["ssl"] = {"ca": os.environ["RDS_SSL_CA"], "check_hostname": True}
    engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
    sessions = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="小智体检云端", version="0.1.0", lifespan=lifespan)

    def authorize(x_api_key: str = Header(default="")):
        if not hmac.compare_digest(x_api_key.encode(), api_key.encode()):
            raise HTTPException(401, "Invalid API key")

    protected = [Depends(authorize)]

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "xiaozhi-health-exam"}

    @app.get("/")
    def index():
        return FileResponse(HERE / "index.html")

    @app.post("/api/exams", dependencies=protected)
    def ingest(payload: ExamInput):
        key = hashlib.sha256(f"{payload.instrument_id}\0{payload.id}".encode()).hexdigest()
        values = {
            "instrument_id": payload.instrument_id,
            "source_record_id": payload.id,
            "height_cm": payload.height_cm,
            "weight_kg": payload.weight_kg,
            "measured_at": payload.timestamp,
            "source": payload.source,
        }
        with sessions() as session:
            existing = session.get(Exam, key)
            if existing is None:
                row = Exam(id=key, bmi=calculate_bmi(payload.height_cm, payload.weight_kg),
                           received_at=datetime.now(UTC).replace(tzinfo=None),
                           speech_status="unconfirmed", **values)
                session.add(row)
                try:
                    session.commit()
                    return {"success": True, "duplicate": False, "record": serialize(row)}
                except IntegrityError:
                    session.rollback()
                    existing = session.get(Exam, key)
                    if existing is None:
                        raise
            if any(getattr(existing, k) != v for k, v in values.items()):
                raise HTTPException(409, "Record id already exists with different measurement data")
            return {"success": True, "duplicate": True, "record": serialize(existing)}

    @app.get("/api/exams", dependencies=protected)
    def list_exams(instrument_id: str | None = None, limit: int = Query(50, ge=1, le=500)):
        with sessions() as session:
            stmt = select(Exam)
            if instrument_id:
                stmt = stmt.where(Exam.instrument_id == instrument_id)
            total = session.scalar(select(func.count()).select_from(stmt.subquery()))
            rows = session.scalars(stmt.order_by(Exam.measured_at.desc(), Exam.id).limit(limit))
            return {"records": [serialize(row) for row in rows], "total_count": total}

    @app.get("/api/exams/{record_id}", dependencies=protected)
    def get_exam(record_id: str):
        with sessions() as session:
            row = session.get(Exam, record_id)
            if row is None:
                raise HTTPException(404, "Record not found")
            return serialize(row)

    @app.post("/api/exams/{record_id}/speech-events", dependencies=protected)
    def speech_event(record_id: str, event: SpeechEvent):
        # This endpoint records an explicit report; it does not itself play audio.
        with sessions() as session:
            row = session.get(Exam, record_id)
            if row is None:
                raise HTTPException(404, "Record not found")
            if row.speech_event_id == event.event_id:
                if row.speech_status != event.status:
                    raise HTTPException(409, "Event id reused with a different status")
                return serialize(row)
            if row.speech_status == "device_confirmed" and event.status != "device_confirmed":
                raise HTTPException(409, "Confirmed playback cannot be downgraded")
            row.speech_status = event.status
            row.speech_event_id = event.event_id
            session.commit()
            return serialize(row)

    @app.post("/api/exams/{record_id}/explanation", dependencies=protected)
    async def explanation(record_id: str):
        url = os.environ.get("MAAS_CHAT_URL", "")
        token = os.environ.get("MAAS_API_KEY", "")
        model = os.environ.get("MAAS_MODEL", "")
        if not all((url, token, model)):
            raise HTTPException(503, "MaaS is not configured; no AI result was generated")
        if not url.startswith("https://"):
            raise HTTPException(503, "MaaS requires an HTTPS endpoint")
        with sessions() as session:
            row = session.get(Exam, record_id)
            if row is None:
                raise HTTPException(404, "Record not found")
            record = serialize(row)
        # Only measurements are sent, never a patient name or account identifier.
        facts = {k: record[k] for k in ("height_cm", "weight_kg", "bmi")}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json={
                    "model": model, "stream": False, "messages": [
                        {"role": "system", "content": "你是测量记录说明助手。仅说明所给身高、体重和BMI的含义，不重新计算、不编造历史，不给疾病诊断、用药或个性化治疗建议；信息不足时明确说明。输出简短中文。"},
                        {"role": "user", "content": str(facts)},
                    ],
                })
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Empty model response")
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise HTTPException(502, "MaaS request failed; no fallback result was fabricated") from None
        return {"record_id": record_id, "provider": "Huawei Cloud MaaS", "model": model,
                "text": text, "kind": "ai_generated_explanation", "measurements": facts}

    return app
