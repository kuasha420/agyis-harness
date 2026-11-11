# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Wire-format protobuf & JSON metadata decoders for Antigravity conversation DBs.
Pure stdlib, zero third-party protobuf runtime dependency (ADR-014 / ADR-035).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass(frozen=True)
class ProtobufUsageMetrics:
    """Decoded token, context window, and model telemetry from protobuf blobs."""

    input_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0
    estimated_tokens: int = 0
    max_context_tokens: int = 0
    checkpoint_idx: int = 0
    model_name: str = ""

    @property
    def total_prompt_tokens(self) -> int:
        """Authoritative active context tokens seen by the model API."""
        return self.input_tokens + self.cache_read_tokens


def parse_protobuf_varint(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Parses a single base-128 protobuf varint starting at offset."""
    res = 0
    shift = 0
    idx = offset
    while idx < len(data):
        b = data[idx]
        idx += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return res, idx


def _read_varint_checked(data: bytes, offset: int) -> Optional[Tuple[int, int]]:
    res = 0
    shift = 0
    idx = offset
    while idx < len(data):
        b = data[idx]
        idx += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            return res, idx
        shift += 7
        if shift > 70:
            return None
    return None


def parse_pb_fields(buf: bytes) -> Optional[List[Tuple[int, int, Any]]]:
    """Strictly decodes top-level protobuf fields; returns None on malformed input."""
    if not buf or not isinstance(buf, bytes):
        return None
    fields: List[Tuple[int, int, Any]] = []
    idx = 0
    while idx < len(buf):
        tv = _read_varint_checked(buf, idx)
        if tv is None:
            return None
        tag, idx = tv
        fn, wt = tag >> 3, tag & 0x07
        if fn == 0:
            return None
        if wt == 0:
            vv = _read_varint_checked(buf, idx)
            if vv is None:
                return None
            val, idx = vv
            fields.append((fn, wt, val))
        elif wt == 2:
            lv = _read_varint_checked(buf, idx)
            if lv is None:
                return None
            length, idx = lv
            if length < 0 or idx + length > len(buf):
                return None
            fields.append((fn, wt, buf[idx : idx + length]))
            idx += length
        elif wt == 1:
            if idx + 8 > len(buf):
                return None
            fields.append((fn, wt, buf[idx : idx + 8]))
            idx += 8
        elif wt == 5:
            if idx + 4 > len(buf):
                return None
            fields.append((fn, wt, buf[idx : idx + 4]))
            idx += 4
        else:
            return None
    return fields


def iter_pb_strings(buf: bytes, *, max_depth: int = 4, min_len: int = 1) -> List[str]:
    """Recursively extracts plausible UTF-8 strings from nested protobuf messages."""
    found: List[str] = []

    def _walk(raw: bytes, depth: int) -> None:
        fields = parse_pb_fields(raw)
        if not fields:
            return
        for _, wt, val in fields:
            if wt != 2 or not isinstance(val, bytes) or not val:
                continue
            nested = parse_pb_fields(val) if depth < max_depth else None
            if nested and any(fn > 0 for fn, _, _ in nested) and _looks_binary_msg(val, nested):
                _walk(val, depth + 1)
                continue
            try:
                text = val.decode("utf-8")
            except UnicodeDecodeError:
                if depth < max_depth and nested:
                    _walk(val, depth + 1)
                continue
            if len(text.strip()) >= min_len and sum(1 for c in text if ord(c) < 32 and c not in "\n\r\t") == 0:
                found.append(text)
            elif depth < max_depth and nested:
                _walk(val, depth + 1)

    _walk(buf, 0)
    return found


def _looks_binary_msg(raw: bytes, fields: List[Tuple[int, int, Any]]) -> bool:
    """Heuristic separating nested protobuf submessages from plain UTF-8 prose."""
    if not fields:
        return False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return True
    # Pure ASCII prose often starts with printable ASCII tags; require small sensible field numbers.
    return all(1 <= fn <= 64 and wt in (0, 1, 2, 5) for fn, wt, _ in fields[:4]) and any(
        b < 32 and b not in (9, 10, 13) for b in raw[:32]
    )


def extract_timestamp_from_protobuf(raw_bytes: bytes) -> Optional[float]:
    """Extracts Unix epoch seconds from steps.metadata protobuf google.protobuf.Timestamp."""
    outer = parse_pb_fields(raw_bytes)
    if not outer:
        return None
    by_fn = {fn: val for fn, wt, val in outer if wt == 2 and isinstance(val, bytes)}
    for fn in (1, 6, 7, 8, 32):
        ts_buf = by_fn.get(fn)
        if not ts_buf:
            continue
        sub = parse_pb_fields(ts_buf)
        if not sub:
            continue
        sec = 0
        nanos = 0
        for sfn, swt, sval in sub:
            if swt == 0 and isinstance(sval, int):
                if sfn == 1:
                    sec = sval
                elif sfn == 2:
                    nanos = sval
        if sec > 1_000_000_000:
            return float(sec) + float(nanos) / 1e9
    return None


def _parse_usage_msg(buf: bytes) -> Tuple[int, int, int, int]:
    """Parses UsageMetadata message -> (input, cache_read, output, thought)."""
    fields = parse_pb_fields(buf)
    if not fields:
        return 0, 0, 0, 0
    inp = cache = out = thought = candidates = 0
    for fn, wt, val in fields:
        if wt == 0 and isinstance(val, int) and val > 0:
            if fn == 2:
                inp = val
            elif fn == 3:
                candidates = val
            elif fn == 5:
                cache = val
            elif fn == 9:
                out = val
            elif fn == 10:
                thought = val
    if out == 0 and candidates > 0:
        out = max(0, candidates - thought)
    return inp, cache, out, thought


def _parse_cwm(buf: bytes) -> Tuple[int, int]:
    """Parses contextWindowMetadata -> (estimatedTokensUsed, maxContextTokens)."""
    fields = parse_pb_fields(buf)
    if not fields:
        return 0, 0
    est = mct = 0
    for fn, wt, val in fields:
        if wt == 0 and isinstance(val, int) and val > 0:
            if fn == 1:
                est = val
            elif fn == 4:
                mct = val
    return est, mct


def _parse_csm(buf: bytes) -> Tuple[int, int, int]:
    """Parses chatStartMetadata -> (checkpoint_idx, estimatedTokensUsed, maxContextTokens)."""
    fields = parse_pb_fields(buf)
    if not fields:
        return 0, 0, 0
    ckpt = est = mct = 0
    for fn, wt, val in fields:
        if fn == 1 and wt == 0 and isinstance(val, int) and val > 0:
            ckpt = val
        elif fn == 10 and wt == 2 and isinstance(val, bytes):
            c_est, c_mct = _parse_cwm(val)
            est = est or c_est
            mct = mct or c_mct
    return ckpt, est, mct


def extract_usage_from_protobuf(raw_bytes: bytes) -> ProtobufUsageMetrics:
    """Decodes UsageMetadata, contextWindowMetadata, checkpoint index, and model from protobuf."""
    outer = parse_pb_fields(raw_bytes)
    if not outer:
        return ProtobufUsageMetrics()

    inp = cache = out = thought = est = mct = ckpt = 0
    model = ""

    for fn, wt, val in outer:
        if wt != 2 or not isinstance(val, bytes):
            continue
        if fn == 1:
            f1_fields = parse_pb_fields(val) or []
            for sfn, swt, sval in f1_fields:
                if swt != 2 or not isinstance(sval, bytes):
                    continue
                if sfn == 9:
                    c_ckpt, c_est, c_mct = _parse_csm(sval)
                    ckpt = ckpt or c_ckpt
                    est = est or c_est
                    mct = mct or c_mct
                elif sfn == 4 and inp == 0 and cache == 0:
                    inp, cache, out, thought = _parse_usage_msg(sval)
                elif sfn == 17 and inp == 0 and cache == 0:
                    for ssfn, sswt, ssval in parse_pb_fields(sval) or []:
                        if ssfn == 2 and sswt == 2 and isinstance(ssval, bytes):
                            inp, cache, out, thought = _parse_usage_msg(ssval)
                            break
                elif sfn in (19, 21) and not model:
                    try:
                        model = sval.decode("utf-8")
                    except UnicodeDecodeError:
                        pass
        elif fn == 9:
            u_in, u_ca, u_out, u_th = _parse_usage_msg(val)
            if u_in + u_ca > 0:
                inp, cache, out, thought = u_in, u_ca, u_out, u_th
            _, c_est, c_mct = _parse_csm(val)
            mct = mct or c_mct
            if u_in == 0 and u_ca == 0 and c_est > 0 and est == 0:
                est = c_est
        elif fn == 10:
            c_est, c_mct = _parse_cwm(val)
            est = est or c_est
            mct = mct or c_mct
        elif fn in (19, 21) and not model:
            try:
                model = val.decode("utf-8")
            except UnicodeDecodeError:
                pass

    return ProtobufUsageMetrics(
        input_tokens=inp,
        cache_read_tokens=cache,
        output_tokens=out,
        thought_tokens=thought,
        estimated_tokens=est,
        max_context_tokens=mct,
        checkpoint_idx=ckpt,
        model_name=model,
    )


def extract_context_window_from_protobuf_metadata(raw_bytes: bytes) -> Tuple[int, int]:
    """Compatibility helper returning (estimatedTokensUsed, maxContextTokens)."""
    metrics = extract_usage_from_protobuf(raw_bytes)
    return metrics.estimated_tokens, metrics.max_context_tokens


def extract_tokens_from_protobuf_metadata(raw_bytes: bytes) -> int:
    """Returns authoritative prompt+cached UsageMetadata tokens, else contextWindowMetadata estimate."""
    metrics = extract_usage_from_protobuf(raw_bytes)
    if metrics.total_prompt_tokens > 0:
        return metrics.total_prompt_tokens
    return metrics.estimated_tokens


def extract_compaction_summary_from_protobuf(raw_bytes: bytes) -> str:
    """Extracts compaction <summary> prose from a checkpoint step_payload blob."""
    if not raw_bytes or not isinstance(raw_bytes, bytes):
        return ""
    fields = parse_pb_fields(raw_bytes)
    if fields:
        for fn, wt, val in fields:
            if fn == 30 and wt == 2 and isinstance(val, bytes):
                for sfn, swt, sval in parse_pb_fields(val) or []:
                    if sfn == 5 and swt == 2 and isinstance(sval, bytes):
                        try:
                            return sval.decode("utf-8", errors="replace").strip()
                        except Exception:
                            pass
    for text in iter_pb_strings(raw_bytes, min_len=20):
        if "<summary>" in text or "# Task Overview" in text or "Task Overview" in text:
            return text.strip()
    strings = [s.strip() for s in iter_pb_strings(raw_bytes, min_len=40)]
    return max(strings, key=len) if strings else ""


def extract_context_window_from_json(data: Any) -> Tuple[int, int]:
    """Extracts (estimatedTokensUsed, maxContextTokens) from JSON metadata structures."""
    if not isinstance(data, dict):
        return 0, 0

    def _to_pos_int(val: Any) -> int:
        if isinstance(val, (int, float)) and int(val) > 0:
            return int(val)
        if isinstance(val, str) and val.strip().isdigit() and int(val.strip()) > 0:
            return int(val.strip())
        return 0

    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    csm = data.get("chatStartMetadata") if isinstance(data.get("chatStartMetadata"), dict) else {}
    meta_csm = meta.get("chatStartMetadata") if isinstance(meta.get("chatStartMetadata"), dict) else {}
    gen = data.get("generator_metadata") if isinstance(data.get("generator_metadata"), dict) else {}
    gen_csm = gen.get("chatStartMetadata") if isinstance(gen.get("chatStartMetadata"), dict) else {}
    gen_meta = gen.get("metadata") if isinstance(gen.get("metadata"), dict) else {}
    gen_meta_csm = gen_meta.get("chatStartMetadata") if isinstance(gen_meta.get("chatStartMetadata"), dict) else {}

    est = mct = 0
    for cwm in (
        data.get("contextWindowMetadata"),
        csm.get("contextWindowMetadata"),
        meta.get("contextWindowMetadata"),
        meta_csm.get("contextWindowMetadata"),
        gen.get("contextWindowMetadata"),
        gen_csm.get("contextWindowMetadata"),
        gen_meta.get("contextWindowMetadata"),
        gen_meta_csm.get("contextWindowMetadata"),
    ):
        if not isinstance(cwm, dict):
            continue
        est = est or _to_pos_int(cwm.get("estimatedTokensUsed") or cwm.get("estimated_tokens_used"))
        mct = mct or _to_pos_int(cwm.get("maxContextTokens") or cwm.get("max_context_tokens"))
        if est > 0 and mct > 0:
            break

    est = est or _to_pos_int(data.get("estimatedTokensUsed") or data.get("estimated_tokens_used"))
    mct = mct or _to_pos_int(data.get("maxContextTokens") or data.get("max_context_tokens"))
    return est, mct


def extract_tool_from_protobuf(raw_bytes: bytes) -> Tuple[str, str]:
    """Extracts (tool_name, tool_args) from Antigravity step metadata protobuf (fn 4)."""
    if not raw_bytes or not isinstance(raw_bytes, (bytes, bytearray, memoryview)):
        return "", ""
    for fn, wt, val in parse_pb_fields(bytes(raw_bytes)) or []:
        if fn == 4 and wt == 2 and isinstance(val, bytes):
            name = args = ""
            for sfn, swt, sval in parse_pb_fields(val) or []:
                if swt != 2 or not isinstance(sval, bytes):
                    continue
                if sfn == 2:
                    name = sval.decode("utf-8", errors="replace")
                elif sfn == 3:
                    args = sval.decode("utf-8", errors="replace")
            if name:
                return name, args
    return "", ""
