#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_WHERE = "Kick · Twitch · YouTube"

TYPE_PATTERNS = [
    (re.compile(r"^\s*\[(MLB|F1|FE|BUILD|GAME)\]\s*", re.I), 1),
    (re.compile(r"^\s*(MLB|F1|FE|BUILD|GAME)\s*[:|]\s*", re.I), 1),
]

def fetch_ics(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "thomsfoolery-schedule-sync/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return raw.decode("utf-8", errors="replace")

def unfold_ics(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        if not line:
            continue
        if (line.startswith(" ") or line.startswith("\t")) and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out

def parse_prop(line: str) -> tuple[str, dict[str, str], str]:
    if ":" not in line:
        return line.strip().upper(), {}, ""
    left, value = line.split(":", 1)
    parts = left.split(";")
    key = parts[0].strip().upper()
    params: dict[str, str] = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip()
    return key, params, value.strip()

def parse_dt(value: str, tzid: str | None) -> datetime | None:
    value = value.strip()
    if re.fullmatch(r"\d{8}$", value):
        return None

    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)

    dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
    if tzid:
        try:
            z = ZoneInfo(tzid)
        except Exception:
            z = timezone.utc
        return dt.replace(tzinfo=z).astimezone(timezone.utc)

    return dt.replace(tzinfo=timezone.utc)

def unescape_ics_text(s: str) -> str:
    return (s.replace(r"\n", " ")
             .replace(r"\N", " ")
             .replace(r"\,", ",")
             .replace(r"\;", ";")
             .strip())

def infer_type(summary: str, desc: str) -> str | None:
    s = summary.strip()
    for rx, grp in TYPE_PATTERNS:
        m = rx.search(s)
        if m:
            return m.group(grp).upper()

    text = f"{summary} {desc}".lower()
    if "#mlb" in text:
        return "MLB"
    if "#f1" in text:
        return "F1"
    if "#fe" in text or "#formulae" in text:
        return "FE"
    if "#build" in text:
        return "BUILD"
    if "#game" in text:
        return "GAME"
    return None

def infer_note(summary: str, desc: str) -> str:
    text = f"{summary} {desc}".lower()
    if "#replay" in text or "[replay]" in text or "replay:" in text:
        return "Replay"
    return "Live"

def strip_type_prefix(summary: str) -> str:
    s = summary.strip()
    for rx, _ in TYPE_PATTERNS:
        s = rx.sub("", s)
    return s.strip()

def ics_to_items(ics_text: str, now_utc: datetime, window_days: int) -> list[dict]:
    lines = unfold_ics(ics_text)
    items: list[dict] = []
    in_event = False
    ev: dict[str, tuple[dict[str, str], str]] = {}

    def flush_event():
        nonlocal ev
        if not ev:
            return

        summary = unescape_ics_text(ev.get("SUMMARY", ({}, ""))[1] or "")
        if not summary:
            ev = {}
            return

        dt_params, dt_val = ev.get("DTSTART", ({}, ""))  # type: ignore
        tzid = dt_params.get("TZID")
        start = parse_dt(dt_val, tzid)
        if not start:
            ev = {}
            return

        if start < now_utc - timedelta(days=1):
            ev = {}
            return
        if start > now_utc + timedelta(days=window_days):
            ev = {}
            return

        location = unescape_ics_text(ev.get("LOCATION", ({}, ""))[1] or "")
        desc = unescape_ics_text(ev.get("DESCRIPTION", ({}, ""))[1] or "")

        t = infer_type(summary, desc)
        note = infer_note(summary, desc)
        title = strip_type_prefix(summary)

        items.append({
            "title": title,
            "when": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "where": location if location else DEFAULT_WHERE,
            "type": t if t else "STREAM",
            "note": note,
        })
        ev = {}

    for line in lines:
        line = line.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            ev = {}
            continue
        if line == "END:VEVENT":
            if in_event:
                flush_event()
            in_event = False
            continue
        if not in_event:
            continue

        key, params, value = parse_prop(line)
        if key in {"SUMMARY", "DTSTART", "LOCATION", "DESCRIPTION"}:
            ev[key] = (params, value)

    items.sort(key=lambda x: x["when"])
    return items

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ics-url", default=os.environ.get("SCHEDULE_ICS_URL", "").strip())
    ap.add_argument("--out", default="content/schedule.json")
    ap.add_argument("--days", type=int, default=int(os.environ.get("SCHEDULE_WINDOW_DAYS", "120")))
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    if not args.ics_url:
        print("Missing ICS URL. Set SCHEDULE_ICS_URL env var or pass --ics-url.", file=sys.stderr)
        return 2

    now_utc = datetime.now(timezone.utc)
    ics = fetch_ics(args.ics_url)
    items = ics_to_items(ics, now_utc=now_utc, window_days=args.days)[: args.limit]

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    payload = {"items": items}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    print(f"Wrote {len(items)} items to {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
