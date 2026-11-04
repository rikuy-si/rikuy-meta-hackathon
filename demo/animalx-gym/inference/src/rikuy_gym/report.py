"""muse-spark-1.3 answers the owner's question over the audit.

Only aggregates and event ids go to the model: no frames, no identities. The
answer cites events as ``[E07]`` / ``[R05]`` / ``[X07]`` so the viewer can turn
them into jump links. Returned in English and Spanish.

Endpoint: OpenAI Responses-compatible. Configure with
``MUSE_BASE_URL`` and ``MUSE_API_KEY`` (never commit them).
"""

from __future__ import annotations

import json
import os
import time

import httpx

MODEL = "muse-spark-1.3"

PROMPT = """You are Rikuy, reviewing a gym entrance camera against the access-control log.
Question from the owner: {question}

Audit (camera entries/exits measured on-premises, access log per minute, already paired):
{facts}

Write a short answer (max 90 words) in {lang}:
- State camera entries and exits, and the rush window with its entry count in **bold**.
- State access records and how many pair to camera entries.
- State the gap to reconcile: unrecorded entries in the validated window and phantom records.
- Cite 3-4 concrete events by id in square brackets, e.g. [E07], [R05], [X07]. Use only ids listed below.
- Never guess identities or intent. End with: these findings await the owner's review.
Return only the answer text."""


def facts(audit: dict) -> str:
    s = audit["stats"]
    sample = {
        "unrecorded_validated": [e["id"] for e in audit["entries"]
                                 if e["verdict"] == "unrecorded" and e["validated"]][:5],
        "recorded": [e["id"] for e in audit["entries"] if e["verdict"] == "recorded"][:3],
        "phantom_records": [r["id"] for r in audit["records"] if r["verdict"] == "phantom"][:5],
        "exits": [f"X{i:02d}" for i in range(1, len(audit["exits"]) + 1)][:10],
    }
    return json.dumps({"stats": s, "event_ids": sample}, ensure_ascii=False)


def ask(audit: dict, question: dict[str, str], *, base_url: str | None = None, api_key: str | None = None,
        timeout: float = 120.0) -> dict:
    base_url = (base_url or os.environ["MUSE_BASE_URL"]).rstrip("/")
    api_key = api_key or os.environ["MUSE_API_KEY"]
    answer, usage, request_id, t0 = {}, {}, None, time.monotonic()
    with httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {api_key}"}) as http:
        for lang, name in (("en", "English"), ("es", "Spanish")):
            body = {"model": MODEL, "input": PROMPT.format(question=question[lang], facts=facts(audit), lang=name)}
            r = http.post(f"{base_url}/responses", json=body)
            r.raise_for_status()
            data = r.json()
            answer[lang] = output_text(data).strip()
            usage = data.get("usage", usage)
            request_id = data.get("id", request_id)
    return {"question": question, "answer": answer, "model": MODEL,
            "latency_s": round(time.monotonic() - t0, 1), "request_id": request_id, "usage": usage}


def output_text(data: dict) -> str:
    if "output_text" in data:
        return data["output_text"]
    return "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []))
