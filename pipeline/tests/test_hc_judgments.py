"""Tests for the open-High-Court judgment source (§4a) — all offline.

Exercises the local statute pre-filter (the cost control), PDF-URL extraction, the
stdin->stdout pdftotext wrapper (via an injected runner AND the real binary on a tiny
synthetic PDF), and the polite listing walk with its per-court/per-run budgets — with a
fake HTTP client, so no network and no real court is ever touched.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from typing import Any

import httpx
import pytest

from pipeline.sources.hc_judgments import (
    HcCourt,
    HcJudgmentsSource,
    extract_pdf_urls,
    pdf_to_text,
    qualifies,
)

# A minimal, valid one-page PDF whose visible text is "POCSO section 376 rape". Synthetic —
# no real case, no PII (CLAUDE.md §2/§3). Used to prove the real pdftotext binary path.
_TINY_PDF = (
    b"%PDF-1.1\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 52>>stream\n"
    b"BT /F1 12 Tf 20 100 Td (POCSO section 376 rape) Tj ET\n"
    b"endstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --- qualifies() — the local statute pre-filter ---------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Charged under POCSO Act, 2012",
        "convicted under BNS Section 64",
        "offence u/s 376 IPC read with section 6 POCSO",
        "IPC 376 and 354A",
        "376 IPC",
        "under section 375",
        "a case of gang-rape",
        "penetrative sexual assault of the child",
        "charge of outraging her modesty under 354",
        "BNS 70(1) gang rape",
    ],
)
def test_qualifies_matches_charged_sexual_offences(text: str) -> None:
    assert qualifies(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "A civil suit for recovery of possession under the Transfer of Property Act",
        "bail application in a cheque-bounce matter under section 138 NI Act",
        "income tax appeal under section 260A",
    ],
)
def test_qualifies_rejects_non_sexual_offence_text(text: str) -> None:
    assert qualifies(text) is False


# --- extract_pdf_urls() ----------------------------------------------------------------------


def test_extract_pdf_urls_resolves_dedupes_and_preserves_order() -> None:
    html_page = """
      <a href="/app/showFileJudgment/AAA.pdf">one</a>
      <a href='https://x.nic.in/b.pdf?ver=2'>two</a>
      <a href="/app/showFileJudgment/AAA.pdf">dup</a>
      <a href="/notes.txt">skip</a>
    """
    urls = extract_pdf_urls(html_page, "https://x.nic.in")
    assert urls == [
        "https://x.nic.in/app/showFileJudgment/AAA.pdf",
        "https://x.nic.in/b.pdf?ver=2",
    ]


def test_extract_pdf_urls_unescapes_entities_and_takes_first_of_concatenated() -> None:
    # Meghalaya quirk: a comma-concatenated multi-file href resolves to its FIRST pdf.
    html_page = '<a href="/files/2014/01-01-2014.pdf,/files/2014/02-01-2014.pdf">x</a>'
    assert extract_pdf_urls(html_page, "https://m.nic.in") == [
        "https://m.nic.in/files/2014/01-01-2014.pdf"
    ]


def test_extract_pdf_urls_empty_is_empty() -> None:
    assert extract_pdf_urls("", "https://x.nic.in") == []


# --- pdf_to_text() ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext (poppler) not installed")
def test_pdf_to_text_real_binary_reads_from_stdin() -> None:
    # Integration proof WHERE poppler exists: the real pdftotext, PDF piped via
    # stdin -> stdout (never a temp file). Skipped where the binary is absent (e.g. CI
    # without poppler); the default-runner branch is covered deterministically below.
    assert "POCSO" in pdf_to_text(_TINY_PDF)


def test_pdf_to_text_default_runner_is_subprocess_run(monkeypatch: pytest.MonkeyPatch) -> None:
    # Covers the run=None branch (runner := subprocess.run) with NO dependency on the
    # binary, so coverage of the default path holds on a runner without poppler.
    def fake_run(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=b"POCSO 376", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert pdf_to_text(_TINY_PDF) == "POCSO 376"


def test_pdf_to_text_empty_bytes_short_circuits() -> None:
    assert pdf_to_text(b"") == ""


def test_pdf_to_text_injected_runner_decodes_stdout() -> None:
    def fake(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=b"hello", stderr=b"")

    assert pdf_to_text(b"%PDF", run=fake) == "hello"


def test_pdf_to_text_missing_binary_returns_empty() -> None:
    def boom(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[bytes]:
        raise FileNotFoundError("pdftotext not installed")

    assert pdf_to_text(b"%PDF", run=boom) == ""


def test_pdf_to_text_timeout_returns_empty() -> None:
    def slow(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(cmd="pdftotext", timeout=1.0)

    assert pdf_to_text(b"%PDF", run=slow) == ""


def test_pdf_to_text_error_returncode_without_output_is_empty() -> None:
    def failed(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout=b"", stderr=b"boom")

    assert pdf_to_text(b"%PDF", run=failed) == ""


def test_pdf_to_text_error_returncode_with_output_is_kept() -> None:
    # A "Syntax Warning" often accompanies rc!=0 but still yields usable text.
    def warned(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=[], returncode=2, stdout=b"POCSO", stderr=b"warn")

    assert pdf_to_text(b"%PDF", run=warned) == "POCSO"


# --- HcJudgmentsSource.fetch() ---------------------------------------------------------------


class _FakeClient:
    """Maps URL -> httpx.Response (or None for a robots-disallowed URL)."""

    def __init__(self, responses: dict[str, httpx.Response | None]) -> None:
        self._responses = responses
        self.gets: list[str] = []

    async def get(self, url: str) -> httpx.Response | None:
        self.gets.append(url)
        return self._responses.get(url)


_LISTING = '<a href="/j/qualify.pdf">a</a><a href="/j/skip.pdf">b</a><a href="/j/missing.pdf">c</a>'
_BASE = "https://court.nic.in"


def _text_for(pdf_bytes: bytes) -> str:
    # Fake pdftotext: the bytes ARE the "text" for the source-level tests.
    return pdf_bytes.decode()


def _pdf(text: str) -> httpx.Response:
    return httpx.Response(200, content=text.encode())


def test_fetch_keeps_only_qualifying_docs_and_records_counts() -> None:
    court = HcCourt("Delhi High Court", f"{_BASE}/list", _BASE)
    client = _FakeClient(
        {
            f"{_BASE}/list": httpx.Response(200, text=_LISTING),
            f"{_BASE}/j/qualify.pdf": _pdf("judgment: convicted under section 376 IPC"),
            f"{_BASE}/j/skip.pdf": _pdf("a civil property dispute, no offence"),
            f"{_BASE}/j/missing.pdf": None,  # robots-disallowed -> skipped
        }
    )
    src = HcJudgmentsSource(client, (court,), fetched_at="2026-08-03", pdf_to_text_fn=_text_for)
    docs = _run(src.fetch())

    assert len(docs) == 1
    assert docs[0].url == f"{_BASE}/j/qualify.pdf"
    assert docs[0].publisher == "Delhi High Court"  # -> classifies as court-grade (tier 1)
    assert docs[0].fetched_at == "2026-08-03"
    # Counts only — never a dropped URL, never any text.
    assert src.stats["Delhi High Court"] == {
        "listed": 3,
        "fetched": 2,
        "pdf_text_empty": 0,
        "not_qualifying": 1,
        "qualifying": 1,
    }


def test_fetch_disallowed_or_error_listing_yields_zero() -> None:
    court = HcCourt("High Court of Meghalaya", f"{_BASE}/none", _BASE)
    client = _FakeClient({f"{_BASE}/none": None})  # robots-disallowed listing
    src = HcJudgmentsSource(client, (court,), pdf_to_text_fn=_text_for)
    assert _run(src.fetch()) == []
    assert src.stats["High Court of Meghalaya"] == {
        "listed": 0,
        "fetched": 0,
        "pdf_text_empty": 0,
        "not_qualifying": 0,
        "qualifying": 0,
    }


def test_fetch_non_200_listing_yields_zero() -> None:
    court = HcCourt("HC", f"{_BASE}/l", _BASE)
    client = _FakeClient({f"{_BASE}/l": httpx.Response(503, text="down")})
    src = HcJudgmentsSource(client, (court,), pdf_to_text_fn=_text_for)
    assert _run(src.fetch()) == []
    assert src.stats["HC"]["listed"] == 0


def test_fetch_skips_non_200_pdf() -> None:
    court = HcCourt("HC", f"{_BASE}/l", _BASE)
    client = _FakeClient(
        {
            f"{_BASE}/l": httpx.Response(200, text='<a href="/x.pdf">x</a>'),
            f"{_BASE}/x.pdf": httpx.Response(404, content=b"gone"),
        }
    )
    src = HcJudgmentsSource(client, (court,), pdf_to_text_fn=_text_for)
    assert _run(src.fetch()) == []
    assert src.stats["HC"] == {
        "listed": 1,
        "fetched": 0,
        "pdf_text_empty": 0,
        "not_qualifying": 0,
        "qualifying": 0,
    }


def test_fetch_respects_per_court_fetch_cap() -> None:
    court = HcCourt("HC", f"{_BASE}/l", _BASE)
    listing = "".join(f'<a href="/j/{i}.pdf">x</a>' for i in range(5))
    responses: dict[str, httpx.Response | None] = {f"{_BASE}/l": httpx.Response(200, text=listing)}
    for i in range(5):
        responses[f"{_BASE}/j/{i}.pdf"] = _pdf("section 376 IPC")
    src = HcJudgmentsSource(
        _FakeClient(responses), (court,), pdf_to_text_fn=_text_for, max_fetch_per_court=2
    )
    docs = _run(src.fetch())
    assert len(docs) == 2  # only the 2 newest fetched, though 5 are listed
    assert src.stats["HC"] == {
        "listed": 5,
        "fetched": 2,
        "pdf_text_empty": 0,
        "not_qualifying": 0,
        "qualifying": 2,
    }


def test_fetch_respects_global_run_budget_across_courts() -> None:
    a = HcCourt("HC-A", f"{_BASE}/a", _BASE)
    b = HcCourt("HC-B", f"{_BASE}/b", _BASE)
    responses: dict[str, httpx.Response | None] = {
        f"{_BASE}/a": httpx.Response(200, text='<a href="/a1.pdf">x</a><a href="/a2.pdf">y</a>'),
        f"{_BASE}/b": httpx.Response(200, text='<a href="/b1.pdf">z</a>'),
        f"{_BASE}/a1.pdf": _pdf("POCSO"),
        f"{_BASE}/a2.pdf": _pdf("POCSO"),
        f"{_BASE}/b1.pdf": _pdf("POCSO"),
    }
    src = HcJudgmentsSource(_FakeClient(responses), (a, b), pdf_to_text_fn=_text_for, max_docs=1)
    docs = _run(src.fetch())
    assert len(docs) == 1  # global budget of 1 stops after HC-A's first qualifying doc
    assert src.stats["HC-B"]["fetched"] == 0  # budget exhausted before HC-B is walked


def test_fetch_raises_when_pdftotext_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # §3: with the REAL pdf_to_text (no injected fn) and pdftotext missing, fetch RAISES at
    # startup rather than silently extracting "" from every PDF.
    monkeypatch.setattr("pipeline.sources.hc_judgments.shutil.which", lambda _name: None)
    court = HcCourt("HC", f"{_BASE}/l", _BASE)
    src = HcJudgmentsSource(_FakeClient({}), (court,))  # default (real) pdf_to_text
    with pytest.raises(RuntimeError, match="poppler"):
        _run(src.fetch())


def test_fetch_fails_when_many_pdfs_all_empty() -> None:
    # §3: >10 fetched PDFs that ALL extract 0 characters = broken binary/PDFs, not a quiet
    # docket — the run fails loudly with the reason.
    listing = "".join(f'<a href="/e/{i}.pdf">x</a>' for i in range(12))
    responses: dict[str, httpx.Response | None] = {f"{_BASE}/l": httpx.Response(200, text=listing)}
    for i in range(12):
        responses[f"{_BASE}/e/{i}.pdf"] = _pdf("")  # empty text from every PDF
    src = HcJudgmentsSource(
        _FakeClient(responses),
        (HcCourt("HC", f"{_BASE}/l", _BASE),),
        pdf_to_text_fn=_text_for,
        max_fetch_per_court=12,
    )
    with pytest.raises(RuntimeError, match="extracted 0"):
        _run(src.fetch())


def test_fetch_splits_empty_from_not_qualifying() -> None:
    # A doc with no text -> pdf_text_empty; a doc with text but no statute -> not_qualifying.
    listing = '<a href="/a.pdf">a</a><a href="/b.pdf">b</a>'
    responses: dict[str, httpx.Response | None] = {
        f"{_BASE}/l": httpx.Response(200, text=listing),
        f"{_BASE}/a.pdf": _pdf(""),  # empty
        f"{_BASE}/b.pdf": _pdf("a civil suit, no offence"),  # text, not qualifying
    }
    src = HcJudgmentsSource(
        _FakeClient(responses), (HcCourt("HC", f"{_BASE}/l", _BASE),), pdf_to_text_fn=_text_for
    )
    assert _run(src.fetch()) == []
    assert src.stats["HC"] == {
        "listed": 2,
        "fetched": 2,
        "pdf_text_empty": 1,
        "not_qualifying": 1,
        "qualifying": 0,
    }
