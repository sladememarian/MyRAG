#!/usr/bin/env python
"""End-to-end smoke test against a running instance.

Uploads two generated AI-company .docx files, asks human-style questions,
edits a document, checks history, and deletes the documents again.

Usage:
    E2E_TOKEN=<drf token> .venv/Scripts/python.exe scripts/e2e_check.py
    docker compose exec -T -e E2E_TOKEN=<token> web python scripts/e2e_check.py

Environment:
    E2E_BASE_URL  default http://localhost:8000
    E2E_TOKEN     required DRF token for a staff/superuser account
    E2E_KEEP=1    keep the uploaded documents instead of deleting them
"""
from __future__ import annotations

import io
import os
import sys
import time

import httpx
from docx import Document as DocxDocument

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000").rstrip("/")
TOKEN = os.environ.get("E2E_TOKEN", "")
KEEP = os.environ.get("E2E_KEEP") == "1"
FAILURES: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + label + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILURES.append(label)


def build_docx(paragraphs, table=None) -> bytes:
    doc = DocxDocument()
    for text in paragraphs:
        doc.add_paragraph(text)
    if table:
        grid = doc.add_table(rows=0, cols=len(table[0]))
        for row in table:
            cells = grid.add_row().cells
            for cell, value in zip(cells, row):
                cell.text = value
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


OVERVIEW = [
    "NovaMind AI is an artificial intelligence company founded in 2021 by Maya Chen and Daniel Park.",
    "The company is headquartered in Berlin, Germany, and currently has 42 employees.",
    "NovaMind's flagship product is Nova-1, a large language model built for customer support teams.",
    "Nova-1 costs 29 US dollars per user per month, and every plan includes a 14-day free trial.",
    "NovaMind serves more than 600 customers in 18 countries.",
    "In 2025 the company raised 12 million dollars in a Series A funding round.",
]

HANDBOOK = [
    "Every employee receives 25 days of paid vacation per year, in addition to local public holidays.",
    "Employees may work remotely up to 3 days per week, with manager approval.",
    "Core working hours are 10:00 to 16:00 Central European Time, Monday to Friday.",
    "The support team answers customer tickets from 09:00 to 18:00 CET on weekdays.",
    "Sick leave requires a doctor's note after 2 consecutive days.",
    "Every employee has an annual learning budget of 1,000 dollars.",
]
HANDBOOK_TABLE = [["Policy", "Value"], ["Vacation", "25 days"], ["Remote work", "3 days per week"]]

OVERVIEW_V2 = [
    "NovaMind AI is an artificial intelligence company founded in 2021 by Maya Chen and Daniel Park.",
    "NovaMind's flagship product is now Nova-2, a large language model built for customer support teams.",
    "Nova-2 costs 49 US dollars per user per month, and every plan includes a 21-day free trial.",
    "The company is headquartered in Berlin, Germany, and currently has 42 employees.",
]


def docx_name(label: str) -> str:
    return f"e2e-{label}-{int(time.time())}.docx"


def upload(client: httpx.Client, title: str, paragraphs, table=None) -> dict:
    response = client.post(
        "/api/documents/",
        data={"title": title},
        files={
            "file": (
                docx_name("doc"),
                build_docx(paragraphs, table),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    check(response.status_code == 201, f"upload document: {title}", f"{response.status_code} {response.text[:200]}")
    body = response.json() if response.status_code == 201 else {}
    if body:
        check(body.get("indexed") is True, "document indexed after upload", str(body)[:200])
        check(len(body.get("full_text", "")) > 20, "full text extracted after upload")
    return body


def ask(client: httpx.Client, question: str) -> httpx.Response:
    response = client.post("/api/ask/", json={"question": question})
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    answer = body.get("answer", "")
    sources = [s.get("document_id") for s in body.get("sources", [])]
    print(f"  Q: {question}\n  A: {answer}\n  sources: {sources}")
    return response


def expect_answer(response: httpx.Response, label: str, groups: list[list[str]], doc_id: int) -> None:
    body = response.json() if response.status_code == 200 else {}
    check(response.status_code == 200, f"{label}: HTTP 200", f"{response.status_code} {response.text[:200]}")
    answer = body.get("answer", "").lower()
    check(all(any(alt.lower() in answer for alt in group) for group in groups),
          f"{label}: answer contains expected facts", answer[:200])
    source_ids = [s.get("document_id") for s in body.get("sources", [])]
    check(doc_id in source_ids, f"{label}: sources point at the uploaded document", str(source_ids))


def main() -> int:
    if not TOKEN:
        print("E2E_TOKEN is required. Create one with: docker compose exec web python manage.py drf_create_token <user>")
        return 2

    headers = {"Authorization": f"Token {TOKEN}"}
    timeout = httpx.Timeout(180.0, connect=10.0)
    created: list[int] = []

    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=timeout) as client:
        try:
            health = client.get("/api/health/")
            print(f"\n== Health ==\n{health.json()}")
            check(health.status_code == 200 and health.json() == {"status": "ok"},
                  "health endpoint returns only status")
            suffix = time.strftime("%H%M%S")
            overview_title = f"E2E NovaMind overview {suffix}"
            handbook_title = f"E2E NovaMind handbook {suffix}"

            print("\n== Upload (create) ==")
            overview = upload(client, overview_title, OVERVIEW)
            handbook = upload(client, handbook_title, HANDBOOK, HANDBOOK_TABLE)
            if not overview or not handbook:
                return 1
            overview_id, handbook_id = overview["id"], handbook["id"]
            created = [overview_id, handbook_id]

            listing = client.get("/api/documents/").json()
            listed_ids = [item["id"] for item in listing.get("results", listing if isinstance(listing, list) else [])]
            check(overview_id in listed_ids and handbook_id in listed_ids, "both documents appear in the document list")
            detail = client.get(f"/api/documents/{overview_id}/")
            check(detail.status_code == 200 and detail.json()["title"] == overview_title, "document detail is readable")

            print("\n== Human-style questions ==")
            expect_answer(ask(client, "Who founded NovaMind AI, and when was the company founded?"),
                          "founder/year", [["maya", "chen"], ["2021"]], overview_id)
            expect_answer(ask(client, "How many people work at NovaMind?"),
                          "headcount", [["42"]], overview_id)
            expect_answer(ask(client, "What does Nova-1 cost per user each month?"),
                          "price", [["29"]], overview_id)
            expect_answer(ask(client, "How many paid vacation days do employees get?"),
                          "vacation", [["25"]], handbook_id)
            expect_answer(ask(client, "Can I work from home, and how many days a week?"),
                          "remote work", [["3", "three"]], handbook_id)
            expect_answer(ask(client, "What are the customer support hours?"),
                          "support hours", [["9:00", "09:00", "9 am", "9 to 6", "9-6"], ["18:00", "6 pm", "6:00", "9 to 6", "9-6"]],
                          handbook_id)

            print("\n== Edit ==")
            rename = client.patch(f"/api/documents/{overview_id}/", json={"title": overview_title + " v2"})
            check(rename.status_code == 200 and rename.json()["title"].endswith("v2"), "title edit is saved")
            check(rename.status_code == 200 and "NovaMind" in rename.json()["full_text"], "full text survives title edit")
            check(rename.status_code == 200 and rename.json()["indexed"] is True, "document stays indexed after title edit")

            replaced = client.patch(
                f"/api/documents/{overview_id}/",
                files={"file": (docx_name("overview-v2"), build_docx(OVERVIEW_V2),
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
            replaced_body = replaced.json() if replaced.status_code == 200 else {}
            check(replaced.status_code == 200, "file edit (re-upload) accepted", f"{replaced.status_code} {replaced.text[:200]}")
            check("Nova-2" in replaced_body.get("full_text", ""), "edited file content replaced the old text")
            check(replaced_body.get("indexed") is True, "document re-indexed after file edit")
            expect_answer(ask(client, "What is the price of Nova-2?"), "edited content searchable", [["49"]], overview_id)

            print("\n== Ungrounded question ==")
            unknown = ask(client, "What is the capital of Australia?")
            unknown_body = unknown.json()
            unknown_answer = unknown_body.get("answer", "").lower()
            check(unknown.status_code in (200, 404), "ungrounded question handled", f"{unknown.status_code}")
            check("canberra" not in unknown_answer, "ungrounded answer does not invent a fact")
            if unknown.status_code == 404:
                detail = unknown_body.get("detail", "").lower()
                check("no relevant" in detail or "not contain" in detail,
                      "404 explains that no relevant content was found", detail[:200])
            else:
                check(any(phrase in unknown_answer for phrase in
                          ("not in the", "not mentioned", "no information", "does not contain", "not provided", "cannot find")),
                      "ungrounded answer says the documents do not cover it", unknown_answer[:200])

            print("\n== History ==")
            history = client.get("/api/history/")
            history_body = history.json()
            rows = history_body.get("results", history_body if isinstance(history_body, list) else [])
            check(history.status_code == 200 and len(rows) > 0, "answer history lists past queries")
            answered = next((row for row in rows if row.get("answer")), None)
            check(answered is not None, "history rows include answers")
            if answered:
                one = client.get(f"/api/history/{answered['id']}/")
                check(one.status_code == 200 and one.json().get("answer"),
                      "history detail returns the full answer")

            print("\n== Delete ==")
            for doc_id, label in ((overview_id, "overview"), (handbook_id, "handbook")):
                deleted = client.delete(f"/api/documents/{doc_id}/")
                check(deleted.status_code == 204, f"delete {label} document", str(deleted.status_code))
                gone = client.get(f"/api/documents/{doc_id}/")
                check(gone.status_code == 404, f"deleted {label} document is gone", str(gone.status_code))
            created = []

            after = ask(client, "What is the price of Nova-2?")
            after_ids = [s.get("document_id") for s in after.json().get("sources", [])] if after.status_code == 200 else []
            check(overview_id not in after_ids and handbook_id not in after_ids,
                  "deleted documents no longer appear in retrieval sources", str(after_ids))
        finally:
            if created and KEEP:
                print(f"\nE2E_KEEP=1: leaving documents {created} in place")
            elif created:
                for doc_id in created:
                    client.delete(f"/api/documents/{doc_id}/")

    print("\n== Summary ==")
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("All end-to-end checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
