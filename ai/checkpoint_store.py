"""Locked, atomic single-document checkpoints with explicit compatibility errors."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Protocol, Self


class CheckpointError(RuntimeError):
    """Checkpoint data or persistence could not be trusted."""


class CheckpointMismatchError(CheckpointError):
    """Resume would combine incompatible translations."""


@dataclass(frozen=True)
class CheckpointIdentity:
    input_signature: str
    input_format: str
    segmenter_signature: str
    output_lang: str
    profile: str
    effort: str | None
    system_prompt_hash: str
    protocol: str
    max_batch_chars: int
    separator_overhead: int


@dataclass(frozen=True)
class SegmentRecord:
    translated: str
    profile: str
    provider: str
    backend: str
    model: str
    effort: str | None
    completed_at: str | None
    runtime_version: str | None = None
    requested_effort: str | None = None
    source_verification: str | None = None


class ICheckpointStore(Protocol):
    last_save_bytes: int
    last_save_seconds: float

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def load(
        self,
        identity: CheckpointIdentity,
        *,
        segment_ids: set[str],
        force: bool = False,
        hard_only: bool = False,
        legacy_input_signature: str | None = None,
    ) -> dict[str, SegmentRecord]: ...

    def save(
        self,
        identity: CheckpointIdentity,
        segments: dict[str, SegmentRecord],
        *,
        usage: tuple[str, dict[str, int | None]] | None = None,
    ) -> None: ...


class ICheckpointStoreFactory(Protocol):
    def create(self, directory: Path) -> ICheckpointStore: ...


class FileSystemCheckpointStoreFactory:
    def create(self, directory: Path) -> ICheckpointStore:
        return CheckpointStore(directory)


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise CheckpointError("Expected a checkpoint object")
    return dict(value)


def _text(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise CheckpointError(f"Invalid checkpoint field: {key}")
    return value


def _optional_text(data: dict[str, object], key: str) -> str | None:
    if key not in data:
        raise CheckpointError(f"Missing checkpoint field: {key}")
    return None if data[key] is None else _text(data, key)


def _read(path: Path) -> dict[str, object]:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise CheckpointError(
            f"Cannot read checkpoint {path.name}; preserve it for recovery"
        ) from exc


class CheckpointStore:
    """A run holds the lock from load through its last persistence operation."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._lock: BinaryIO | None = None
        self.last_save_bytes = 0
        self.last_save_seconds = 0.0
        self._usage_by_run: dict[str, object] = {}

    def __enter__(self) -> Self:
        if self._lock is not None:
            raise CheckpointError("Checkpoint store is already open")
        self.directory.mkdir(parents=True, exist_ok=True)
        lock = (self.directory / "checkpoint.lock").open("a+b")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            lock.close()
            raise CheckpointError("Another run owns this checkpoint") from exc
        self._lock = lock
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    def _require_lock(self) -> None:
        if self._lock is None:
            raise CheckpointError("Open the checkpoint store before use")

    def load(
        self,
        identity: CheckpointIdentity,
        *,
        segment_ids: set[str],
        force: bool = False,
        hard_only: bool = False,
        legacy_input_signature: str | None = None,
    ) -> dict[str, SegmentRecord]:
        self._require_lock()
        path = self.directory / "checkpoint.json"
        if not path.exists():
            if (self.directory / "state.json").exists() or (
                self.directory / "translations.json"
            ).exists():
                data = self._import_legacy(
                    identity, force=force, legacy_input_signature=legacy_input_signature
                )
            else:
                return {}
        else:
            data = _read(path)
        if data.get("schema_version") != 2:
            raise CheckpointError("Unsupported checkpoint schema")
        self._usage_by_run = _object(data.get("paid_usage_by_run", {}))
        stored = _object(data.get("identity"))
        expected = asdict(identity)
        if set(stored) != set(expected):
            raise CheckpointError("Incomplete checkpoint identity")
        for key, value in stored.items():
            if key in ("max_batch_chars", "separator_overhead"):
                if type(value) is not int or value < (1 if key == "max_batch_chars" else 0):
                    raise CheckpointError(f"Invalid checkpoint field: {key}")
            elif key == "effort":
                if value not in (None, "low", "medium", "high"):
                    raise CheckpointError("Invalid checkpoint effort")
            elif not isinstance(value, str) or not value:
                raise CheckpointError(f"Invalid checkpoint field: {key}")
        hard = ("input_signature", "input_format", "segmenter_signature")
        mismatches = [key for key in expected if stored[key] != expected[key]]
        if any(key in hard for key in mismatches) or (mismatches and not force and not hard_only):
            raise CheckpointMismatchError("Checkpoint mismatch: " + ", ".join(mismatches))
        records: dict[str, SegmentRecord] = {}
        for segment_id, raw in _object(data.get("segments")).items():
            if segment_id not in segment_ids:
                raise CheckpointError("Checkpoint contains unknown source segment IDs")
            item = _object(raw)
            records[segment_id] = SegmentRecord(
                _text(item, "translated"),
                _text(item, "profile"),
                _text(item, "provider"),
                _text(item, "backend"),
                _text(item, "model"),
                _optional_text(item, "effort"),
                _optional_text(item, "completed_at"),
                _optional_text(item, "runtime_version") if "runtime_version" in item else None,
                _optional_text(item, "requested_effort") if "requested_effort" in item else None,
                _optional_text(item, "source_verification")
                if "source_verification" in item
                else None,
            )
            record = records[segment_id]
            if not record.translated.strip():
                raise CheckpointError("Invalid empty checkpoint translation")
            if (
                record.profile not in ("flash", "pro")
                or record.provider not in ("cli", "api", "legacy_unknown")
                or record.backend
                not in ("antigravity", "gemini_api", "gemini_cli", "legacy_unknown")
            ):
                raise CheckpointError("Invalid checkpoint provenance")
        if type(data.get("translated_segment_count")) is not int or data.get(
            "translated_segment_count"
        ) != len(records):
            raise CheckpointError("Checkpoint segment count does not match its content")
        return records

    def _import_legacy(
        self, identity: CheckpointIdentity, *, force: bool, legacy_input_signature: str | None
    ) -> dict[str, object]:
        state = _read(self.directory / "state.json")
        translations = _read(self.directory / "translations.json")
        if state.get("schema_version") != 1 or translations.get("schema_version") != 1:
            raise CheckpointError("Unsupported legacy checkpoint schema")
        model = _text(state, "model")
        provider = _text(state, "provider")
        profile = {"gemini-2.5-flash": "flash", "gemini-2.5-pro": "pro"}.get(model)
        if profile is None:
            if not force:
                raise CheckpointMismatchError(
                    "Unknown legacy model; select a profile and force resume explicitly"
                )
            profile = identity.profile
        stored: dict[str, object] = {}
        for key in (
            "input_signature",
            "input_format",
            "segmenter_signature",
            "output_lang",
            "system_prompt_hash",
        ):
            stored[key] = _text(state, key)
        for key in ("max_batch_chars", "separator_overhead"):
            value = state.get(key)
            if type(value) is not int:
                raise CheckpointError(f"Missing legacy compatibility field: {key}")
            stored[key] = value
        if legacy_input_signature is None or stored["input_signature"] != legacy_input_signature:
            raise CheckpointMismatchError(
                "Legacy metadata fingerprint mismatch; start with a fresh checkpoint"
            )
        if not force:
            raise CheckpointMismatchError(
                "Legacy checkpoints contain metadata fingerprints, not content hashes; force resume explicitly to accept unverified source content"
            )
        # Explicit import binds future checks to current bytes, without claiming that
        # historical translations were verified against those bytes.
        stored["input_signature"] = identity.input_signature
        stored.update(profile=profile, effort=None)
        stored["protocol"] = (
            "segment_tags"
            if stored["segmenter_signature"] == "epub-leaf-block-v3"
            else "legacy_unknown"
        )
        segments: dict[str, object] = {}
        backend = {"cli": "gemini_cli", "api": "gemini_api"}.get(provider, "legacy_unknown")
        for key, value in _object(translations.get("segments")).items():
            if not isinstance(value, str):
                raise CheckpointError("Invalid legacy translation")
            segments[key] = asdict(
                SegmentRecord(
                    value,
                    profile,
                    provider,
                    backend,
                    model,
                    None,
                    None,
                    source_verification="legacy_metadata_only",
                )
            )
        if type(state.get("translated_segment_count")) is not int or state[
            "translated_segment_count"
        ] != len(segments):
            raise CheckpointError("Legacy metadata and translation counts disagree")
        return {
            "schema_version": 2,
            "identity": stored,
            "segments": segments,
            "translated_segment_count": len(segments),
        }

    def save(
        self,
        identity: CheckpointIdentity,
        segments: dict[str, SegmentRecord],
        *,
        usage: tuple[str, dict[str, int | None]] | None = None,
    ) -> None:
        self._require_lock()
        started = time.monotonic()
        usage_by_run = dict(self._usage_by_run)
        if usage is not None:
            usage_by_run[usage[0]] = usage[1]
        payload = {
            "schema_version": 2,
            "identity": asdict(identity),
            "translated_segment_count": len(segments),
            "segments": {key: asdict(record) for key, record in segments.items()},
            "models_used": sorted({record.model for record in segments.values()}),
            "providers_used": sorted({record.provider for record in segments.values()}),
            "paid_usage_by_run": usage_by_run,
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.directory, prefix=".checkpoint-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / "checkpoint.json")
            descriptor = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise CheckpointError(
                "Checkpoint persistence failed; stop and inspect before resuming"
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.last_save_bytes = len(content)
        self._usage_by_run = usage_by_run
        self.last_save_seconds = time.monotonic() - started
