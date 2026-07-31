"""Tests for the credential backstop (scripts/secret_guard.py, §0).

Fake keys are CONSTRUCTED at runtime (concatenation) so this tracked test file never itself
contains a literal that the guard — or a real scanner — would flag.
"""

from __future__ import annotations

from scripts import secret_guard

# All secret-SHAPED values are built at runtime (never a literal in this tracked file), so
# neither secret_guard nor a third-party scanner ever sees a real-looking string here. Both
# are deliberately low-entropy (repeated chars) yet valid-shaped.
_FAKE_GOOGLE_KEY = "AIza" + "b" * 35  # matches the Google shape, obviously not real
_FAKE_TOKEN = "z" * 24  # >=20 token chars, no placeholder marker -> "looks real" to the guard


def test_google_api_key_is_flagged() -> None:
    findings = secret_guard.scan_text(f"const KEY = '{_FAKE_GOOGLE_KEY}';")
    assert findings and "Google API key" in findings[0][1]


def test_assignment_with_real_value_is_flagged() -> None:
    findings = secret_guard.scan_text("GEMINI_API_KEY=" + _FAKE_TOKEN)
    assert findings and "assignment with a real value" in findings[0][1]


def test_placeholder_and_var_ref_are_clean() -> None:
    assert secret_guard.scan_text("GEMINI_API_KEY=your-key-here") == []
    assert secret_guard.scan_text("GEMINI_API_KEY=${GEMINI_API_KEY}") == []
    assert secret_guard.scan_text("GEMINI_API_KEY=") == []
    assert secret_guard.scan_text("# set GEMINI_API_KEY in the environment") == []


def test_looks_like_secret_value_boundaries() -> None:
    assert secret_guard._looks_like_secret_value(_FAKE_TOKEN) is True
    assert secret_guard._looks_like_secret_value("short") is False  # too short
    assert secret_guard._looks_like_secret_value("test-" + "a" * 16) is False  # placeholder
    assert secret_guard._looks_like_secret_value("has space here now yes") is False  # not token-ish


def test_scan_tracked_tree_is_clean_and_main_exit_codes() -> None:
    """The real repo must have no credential in any tracked file."""
    assert secret_guard.scan_tracked() == []
    assert secret_guard.main([]) == 0
