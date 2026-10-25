"""DS2 header strings are untrusted and must not reach the terminal raw."""

import unicodedata

import pytest

import ds2_to_mp3
from ds2_fixtures import SP_FORMAT, make_ds2, random_payload
from ds2_to_mp3 import sanitize_for_terminal


def test_sanitize_escapes_escape_sequences_and_line_breaks():
    raw = "DPM\x1b[2J\r\n\x07\x7f6000\x9b"

    cleaned = sanitize_for_terminal(raw)

    assert not any(unicodedata.category(c) == 'Cc' for c in cleaned)
    assert "\\x1b[2J" in cleaned
    assert cleaned.startswith("DPM")
    assert cleaned.endswith("6000\\x9b")


def test_sanitize_keeps_ordinary_text_unchanged():
    assert sanitize_for_terminal("Recording 5018 - Müller") == "Recording 5018 - Müller"


@pytest.mark.parametrize("raw, escaped", [
    ("evil‮gnp.exe", "evil\\u202egnp.exe"),        # right-to-left override (Cf)
    ("line break", "line\\u2028break"),            # line separator (Zl)
    ("para break", "para\\u2029break"),            # paragraph separator (Zp)
    ("zero​width", "zero\\u200bwidth"),            # zero-width space (Cf)
    ("private", "priv\\ue000ate"),                # private use (Co)
    ("sur\ud800rogate", "sur\\ud800rogate"),            # surrogate (Cs)
    ("plane\U000f0000ane", "plane\\U000f0000ane"),      # supplementary private use (Co)
])
def test_sanitize_escapes_format_separator_and_private_characters(raw, escaped):
    assert sanitize_for_terminal(raw) == escaped


def test_sanitize_leaves_no_format_or_separator_characters():
    raw = "a‮⁦​  ﻿b"

    cleaned = sanitize_for_terminal(raw)

    assert all(unicodedata.category(c) not in {'Cc', 'Cf', 'Zl', 'Zp', 'Co', 'Cs'} for c in cleaned)


def test_convert_file_prints_no_raw_control_characters(tmp_path, capsys):
    pytest.importorskip("lameenc")
    pytest.importorskip("mutagen")
    data = bytearray(make_ds2([(0, random_payload(1))], SP_FORMAT))
    data[0x0C:0x0C + 12] = b"DPM\x1b[31m\x07X\x00\x00"
    data[0x240:0x240 + 8] = b"Ann\x1b]0;\x07"
    path = tmp_path / "rec.DS2"
    path.write_bytes(bytes(data))

    result = ds2_to_mp3.convert_file(str(path), str(tmp_path))

    captured = capsys.readouterr().out
    assert result is not None
    assert "\x1b" not in captured
    assert "\x07" not in captured
    assert "\\x1b" in captured


def test_convert_file_error_output_is_sanitized(tmp_path, monkeypatch, capsys):
    data = make_ds2([(0, random_payload(1))], SP_FORMAT)
    path = tmp_path / "rec.DS2"
    path.write_bytes(data)

    def failing_decode(self, ds2_path):
        raise ValueError("boom \x1b[2J ‮ end")

    monkeypatch.setattr(ds2_to_mp3.DS2Decoder, "decode_file", failing_decode)

    result = ds2_to_mp3.convert_file(str(path), str(tmp_path))

    captured = capsys.readouterr()
    assert result is None
    assert "ERROR - boom \\x1b[2J \\u202e end" in captured.out
    for stream in (captured.out, captured.err):
        assert "\x1b" not in stream
        assert "‮" not in stream
    # The traceback is kept, with its line breaks, and includes the failing call.
    assert "Traceback (most recent call last)" in captured.err
    assert "failing_decode" in captured.err
    assert "\\x1b[2J" in captured.err
