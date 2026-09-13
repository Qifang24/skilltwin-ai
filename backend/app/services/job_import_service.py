"""Staged, auditable and idempotent job-posting imports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.enums import DataFlag
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.job_market import JobImportBatch, JobImportRow, JobPosting, JobSkillCandidate
from app.models.ontology import Job, Skill
from app.services.job_market_service import JobMarketService

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "source_record_id": ("id", "record_id", "source_record_id", "编号"),
    "title": ("title", "job_title", "position_name", "岗位名称", "职位名称", "岗位"),
    "company_name": ("company", "company_name", "企业名称", "公司名称"),
    "company_type": ("company_type", "企业类型", "公司类型"),
    "city": ("city", "location", "城市", "地区"),
    "raw_text": ("raw_text", "jd", "description", "job_description", "岗位描述", "职位描述"),
    "source_name": ("source", "source_name", "来源", "平台"),
    "source_url": ("url", "source_url", "link", "链接", "来源链接"),
    "posted_at": ("posted_at", "published_at", "publish_time", "date", "发布日期", "发布时间"),
    "salary_text": ("salary", "salary_text", "薪资"),
    "education_req": ("education", "education_req", "学历"),
    "experience_req": ("experience", "experience_req", "经验"),
    "skills": ("skills", "skill", "技能", "技能要求"),
    "data_flag": ("data_flag", "数据类型"),
}

_PII_PATTERNS = (
    re.compile(r"1[3-9]\d{9}"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    re.compile(r"(?i)(微信|weixin|wechat|vx|qq|联系方式)[:：\s]*[A-Za-z0-9_-]{4,}"),
)


def scrub_pii(value: str) -> tuple[str, bool]:
    result = value
    replacements = ("[手机号已脱敏]", "[邮箱已脱敏]", "[联系方式已脱敏]")
    for pattern, replacement in zip(_PII_PATTERNS, replacements):
        result = pattern.sub(replacement, result)
    return result, result != value


def _decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValidationError("CSV 编码无法识别，请使用 UTF-8、UTF-8 BOM 或 GB18030。")


def parse_job_file(filename: str, content: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    if not content:
        raise ValidationError("上传文件为空。")
    if len(content) > MAX_BYTES:
        raise ValidationError("岗位文件超过 10MB 限制。")
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "csv":
        reader = csv.DictReader(io.StringIO(_decode_csv(content)))
        rows = [dict(row) for row in reader]
        headers = list(reader.fieldnames or [])
    elif suffix == "json":
        try:
            payload = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("JSON 文件格式或编码不正确。") from exc
        if isinstance(payload, dict):
            defaults = {k: payload.get(k) for k in ("default_source_name", "default_source_url", "data_flag") if payload.get(k) is not None}
            payload = payload.get("postings")
            if isinstance(payload, list) and defaults:
                payload = [{**defaults, **row, "source_name": row.get("source_name") or defaults.get("default_source_name"), "source_url": row.get("source_url") or defaults.get("default_source_url")} for row in payload]
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise ValidationError("JSON 必须是对象数组，或包含 postings 数组。")
        rows = payload
        headers = list(dict.fromkeys(key for row in rows for key in row))
    else:
        raise ValidationError("岗位导入仅支持 CSV 和 JSON。")
    if not rows:
        raise ValidationError("文件中没有岗位记录。")
    if len(rows) > MAX_ROWS:
        raise ValidationError("岗位文件超过 5000 行限制。")
    return headers, rows


def auto_mapping(headers: list[str]) -> dict[str, str]:
    indexed = {header.strip().casefold(): header for header in headers}
    result: dict[str, str] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias.casefold() in indexed:
                result[canonical] = indexed[alias.casefold()]
                break
    return result


def _parse_date(value: Any) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().replace("/", "-")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("日期格式错误，应为 ISO 日期（例如 2026-09-12）") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def fingerprint(raw_text: str) -> str:
    normalized = re.sub(r"\s+", "", raw_text).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _skill_terms(value: Any) -> list[str]:
    """Normalize CSV delimited text and JSON arrays to the same skill list."""
    values = value if isinstance(value, (list, tuple, set)) else re.split(r"[,，;；|/]", str(value or ""))
    return sorted({str(item).strip() for item in values if str(item).strip()})


class JobImportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, *, filename: str, content: bytes, job_id: str, job_name: str) -> JobImportBatch:
        headers, raw_rows = parse_job_file(filename, content)
        return self.create_records(
            filename=filename,
            records=raw_rows,
            headers=headers,
            job_id=job_id,
            job_name=job_name,
        )

    def create_records(
        self,
        *,
        filename: str,
        records: list[dict[str, Any]],
        job_id: str,
        job_name: str,
        headers: list[str] | None = None,
    ) -> JobImportBatch:
        """Stage already parsed records through the same persisted row pipeline.

        This is the compatibility seam for JSON callers such as the legacy
        ``/job-market/import`` API.  It deliberately does not confirm or commit.
        """
        if not records:
            raise ValidationError("没有可导入的岗位记录。")
        if len(records) > MAX_ROWS:
            raise ValidationError("岗位记录超过 5000 行限制。")
        resolved_headers = headers or list(
            dict.fromkeys(key for record in records for key in record)
        )
        canonical = json.dumps(records, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        batch = JobImportBatch(
            id=f"jib_{uuid.uuid4().hex}", job_id=job_id, job_name=job_name,
            filename=filename, file_hash=hashlib.sha256(canonical).hexdigest(),
            headers=resolved_headers, total_rows=len(records),
            field_mapping=auto_mapping(resolved_headers),
        )
        self.db.add(batch)
        self.db.flush()
        for number, raw in enumerate(records, 1):
            # Scrub the staging area as well; raw uploaded contact data is never persisted.
            safe: dict[str, Any] = {}
            row_was_scrubbed = False
            for key, value in raw.items():
                if isinstance(value, str):
                    scrubbed, changed = scrub_pii(value)
                    safe[key] = scrubbed
                    row_was_scrubbed = row_was_scrubbed or changed
                else:
                    safe[key] = value
            # Internal audit marker; it is not included in headers and therefore
            # cannot be selected as a user field mapping.
            safe["_pii_scrubbed"] = row_was_scrubbed
            self.db.add(JobImportRow(batch_id=batch.id, row_number=number, raw_data=safe))
        self.db.flush()
        self.validate(batch)
        return batch

    def import_legacy_records(
        self,
        *,
        job_id: str,
        job_name: str,
        records: list[dict[str, Any]],
    ) -> tuple[JobImportBatch, Any]:
        """Adapt the original JSON contract without bypassing staged imports.

        Legacy guarantees retained here: explicit posting IDs are preserved,
        a matching ID is updated, duplicates under another ID are skipped, and
        REAL rows still require a publication date and a valid source URL.
        """
        seen_ids: set[str] = set()
        seen_text: set[str] = set()
        prepared: list[dict[str, Any]] = []
        for index, raw in enumerate(records, 1):
            record = dict(raw)
            record_id = str(record.get("id") or "").strip()
            normalized_text = " ".join(str(record.get("raw_text") or "").split())
            if record_id in seen_ids:
                raise ValidationError(f"第 {index} 条岗位记录的 ID 重复：{record_id}")
            if normalized_text in seen_text:
                raise ValidationError(f"第 {index} 条岗位记录与本次导入中的其他 JD 原文重复")
            seen_ids.add(record_id)
            seen_text.add(normalized_text)
            url = str(record.get("source_url") or "").strip()
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValidationError(f"第 {index} 条岗位记录的来源链接必须是有效的 http(s) 地址")
            data_flag = str(record.get("data_flag") or "REAL")
            if data_flag == DataFlag.REAL.value and not record.get("posted_at"):
                raise ValidationError(f"第 {index} 条 REAL 岗位记录缺少发布日期")
            record["source_record_id"] = record_id
            declared = record.pop("skill_codes", None)
            if declared:
                record["skills"] = ",".join(str(code) for code in declared)
            prepared.append(record)

        batch = self.create_records(
            filename="legacy-api.json",
            records=prepared,
            job_id=job_id,
            job_name=job_name,
        )
        rows = self.rows(batch.id)
        invalid = next((row for row in rows if row.status == "invalid"), None)
        if invalid:
            raise ValidationError(
                f"第 {invalid.row_number} 条岗位记录校验失败：{'；'.join(invalid.errors)}"
            )
        # A duplicate owned by the same explicit ID is an update, not a skip.
        for row in rows:
            source_id = str(row.normalized_data.get("source_record_id") or "")
            current = self.db.get(JobPosting, source_id)
            if current is not None:
                row.status = "valid"
        batch.duplicate_count = sum(row.status == "duplicate" for row in rows)
        self.db.flush()
        batch = self.confirm(
            batch.id,
            preserve_source_ids=True,
            allow_updates=True,
            allow_empty=True,
        )
        return batch, JobMarketService(self.db).dashboard(job_id)

    def get(self, batch_id: str) -> JobImportBatch:
        batch = self.db.get(JobImportBatch, batch_id)
        if batch is None:
            raise NotFoundError(f"未找到岗位导入批次：{batch_id}")
        return batch

    def rows(self, batch_id: str) -> list[JobImportRow]:
        return list(self.db.execute(select(JobImportRow).where(JobImportRow.batch_id == batch_id).order_by(JobImportRow.row_number)).scalars())

    def update_mapping(self, batch_id: str, mapping: dict[str, str]) -> JobImportBatch:
        batch = self.get(batch_id)
        if batch.status == "confirmed":
            raise ConflictError("已确认批次不能修改字段映射。")
        unknown = sorted(set(mapping.values()) - set(batch.headers))
        if unknown:
            raise ValidationError("字段映射引用了不存在的列。", detail={"columns": unknown})
        batch.field_mapping = mapping
        self.validate(batch)
        return batch

    def validate(self, batch: JobImportBatch) -> None:
        mapping = batch.field_mapping
        rows = self.rows(batch.id)
        seen: set[str] = set()
        existing_rows = list(
            self.db.execute(
                select(JobPosting.dedupe_hash, JobPosting.raw_text).where(
                    JobPosting.job_id == batch.job_id
                )
            )
        )
        existing = {
            stored_hash or fingerprint(raw_text)
            for stored_hash, raw_text in existing_rows
            if raw_text
        }
        for row in rows:
            data = {field: row.raw_data.get(column) for field, column in mapping.items()}
            errors: list[str] = []
            warnings: list[str] = []
            for required in ("title", "raw_text", "source_name"):
                if not str(data.get(required) or "").strip():
                    errors.append(f"{required} 为必填字段")
            if len(str(data.get("title") or "").strip()) > 255:
                errors.append("岗位名称超过 255 个字符")
            if len(str(data.get("source_name") or "").strip()) > 128:
                errors.append("招聘来源超过 128 个字符")
            city = str(data.get("city") or "").strip()
            if len(city) > 64:
                errors.append("城市字段超过 64 个字符")
            elif city and (
                "http://" in city.casefold()
                or "https://" in city.casefold()
                or "@" in city
                or "已脱敏]" in city
                or re.search(r"1[3-9]\d{9}", city)
            ):
                errors.append("城市字段疑似包含链接或联系方式")
            url = str(data.get("source_url") or "").strip()
            if url:
                parsed = urlparse(url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    errors.append("source_url 必须是有效的 HTTP(S) 地址")
            try:
                posted_at = _parse_date(data.get("posted_at"))
            except ValueError as exc:
                posted_at = None
                errors.append(str(exc))
            if posted_at is None:
                warnings.append("缺少发布日期；记录会进入排名但排除在趋势之外")
            raw_text, was_scrubbed = scrub_pii(str(data.get("raw_text") or "").strip())
            was_scrubbed = bool(row.raw_data.get("_pii_scrubbed")) or was_scrubbed
            data["raw_text"] = raw_text
            data["posted_at"] = posted_at.isoformat() if posted_at else None
            data["pii_scrubbed"] = was_scrubbed
            data["data_flag"] = str(data.get("data_flag") or "REAL").upper()
            data["skills"] = ",".join(_skill_terms(data.get("skills"))) or None
            if data["data_flag"] not in {"REAL", "DEMO"}:
                errors.append("data_flag 只能是 REAL 或 DEMO")
            row_hash = fingerprint(raw_text) if raw_text else None
            status = "invalid" if errors else "valid"
            if row_hash and (row_hash in seen or row_hash in existing):
                status = "duplicate"
                warnings.append("与批内或历史岗位正文重复")
            if row_hash:
                seen.add(row_hash)
            row.normalized_data, row.errors, row.warnings = data, errors, warnings
            row.dedupe_hash, row.status = row_hash, status
        batch.status = "validated"
        batch.failed_count = sum(row.status == "invalid" for row in rows)
        batch.duplicate_count = sum(row.status == "duplicate" for row in rows)
        self.db.flush()

    def confirm(
        self,
        batch_id: str,
        *,
        preserve_source_ids: bool = False,
        allow_updates: bool = False,
        allow_empty: bool = False,
    ) -> JobImportBatch:
        batch = self.get(batch_id)
        if batch.status == "confirmed":
            return batch
        self.validate(batch)
        rows = self.rows(batch.id)
        if allow_updates and preserve_source_ids:
            # validate() correctly sees the existing body as a historical
            # duplicate.  For the legacy API, ownership of that fingerprint by
            # the same explicit record ID means update-in-place instead.
            for row in rows:
                source_id = str(row.normalized_data.get("source_record_id") or "")
                if source_id and self.db.get(JobPosting, source_id) is not None:
                    row.status = "valid"
            batch.duplicate_count = sum(row.status == "duplicate" for row in rows)
        if not allow_empty and not any(row.status == "valid" for row in rows):
            raise ValidationError("批次中没有可导入记录。")
        if self.db.get(Job, batch.job_id) is None:
            self.db.add(Job(id=batch.job_id, name=batch.job_name))
            self.db.flush()
        skills = list(self.db.execute(select(Skill)).scalars())
        known_terms = {term.casefold(): skill.skill_code for skill in skills for term in (skill.skill_code, skill.name_zh, skill.name_en, *skill.aliases) if term}
        created = updated = 0
        for row in rows:
            if row.status != "valid":
                continue
            data = row.normalized_data
            source_record_id = str(data.get("source_record_id") or "").strip() or None
            posting_id = source_record_id if preserve_source_ids and source_record_id else f"jp_{uuid.uuid4().hex}"
            posting_fields = dict(
                job_id=batch.job_id, title=str(data["title"]).strip(),
                company_name=str(data.get("company_name") or "").strip() or None,
                company_type=str(data.get("company_type") or "").strip() or None,
                city=str(data.get("city") or "").strip() or None,
                raw_text=data["raw_text"], source_name=str(data["source_name"]).strip(),
                source_url=str(data.get("source_url") or "").strip() or None,
                posted_at=datetime.fromisoformat(data["posted_at"]) if data.get("posted_at") else None,
                collected_at=datetime.now(timezone.utc), salary_text=data.get("salary_text"),
                education_req=data.get("education_req"), experience_req=data.get("experience_req"),
                data_flag=DataFlag(data.get("data_flag", "REAL")), pii_scrubbed=bool(data.get("pii_scrubbed")),
                import_batch_id=batch.id, source_record_id=source_record_id,
                dedupe_hash=row.dedupe_hash,
                extra={"declared_skills": str(data.get("skills") or "").strip()} if data.get("skills") else {},
            )
            posting = self.db.get(JobPosting, posting_id) if allow_updates else None
            if posting is None:
                posting = JobPosting(id=posting_id, **posting_fields)
                self.db.add(posting)
                created += 1
            else:
                for key, value in posting_fields.items():
                    setattr(posting, key, value)
                updated += 1
            self.db.flush()
            row.posting_id, row.status = posting_id, "imported"
            self.db.execute(
                delete(JobSkillCandidate).where(JobSkillCandidate.posting_id == posting_id)
            )
            for term in _skill_terms(data.get("skills")):
                if term.casefold() not in known_terms:
                    self.db.add(JobSkillCandidate(posting_id=posting_id, candidate_name=term[:128], evidence_span=term))
        # Any extraction/statistics failure aborts the same transaction at the route boundary.
        result = JobMarketService(self.db).analyze(batch.job_id)
        batch.success_count = created
        batch.confirmed_at = datetime.now(timezone.utc)
        batch.status = "confirmed"
        batch.result = {
            "created": created, "updated": updated, "failed": batch.failed_count, "duplicates": batch.duplicate_count,
            "filtered": batch.filtered_count, "snapshots_written": result.snapshots_written,
        }
        self.db.flush()
        return batch
