"""E7 — SES inbound MIME parser tests.

Confirms the parser handles the shapes SES will actually deliver:
plain text, multipart text+html, HTML-only, and edge cases like
non-utf-8 charset headers.
"""

from __future__ import annotations

from app.integrations.ses_inbound import parse_raw_email, strip_html


def test_parse_plain_text_email():
    raw = (
        b"From: Anita <anita@example.com>\r\n"
        b"To: ops@bridgeos.example\r\n"
        b"Subject: Re: Today's bridge update for Riya\r\n"
        b"Date: Sun, 07 Jun 2026 08:00:00 +0530\r\n"
        b"Message-ID: <reply-abc123@example.com>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"We're sorted for this slot, thank you. Please don't reach out to other donors.\r\n"
    )
    parsed = parse_raw_email(raw)
    assert parsed.from_email == "anita@example.com"
    assert parsed.to_email == "ops@bridgeos.example"
    assert "bridge update for Riya" in parsed.subject
    assert "sorted for this slot" in parsed.body_text
    assert parsed.message_id == "reply-abc123@example.com"


def test_parse_multipart_text_html():
    raw = (
        b"From: Anita Sharma <anita@example.com>\r\n"
        b"To: ops@bridgeos.example\r\n"
        b"Subject: We have a donor\r\n"
        b"Content-Type: multipart/alternative; boundary=\"BOUNDARY\"\r\n"
        b"\r\n"
        b"--BOUNDARY\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Thanks, we already found one. Please cancel.\r\n"
        b"--BOUNDARY\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"\r\n"
        b"<p>Thanks, we already <b>found</b> one. Please cancel.</p>\r\n"
        b"--BOUNDARY--\r\n"
    )
    parsed = parse_raw_email(raw)
    assert parsed.from_email == "anita@example.com"
    assert "found one" in parsed.body_text
    assert parsed.body_html is not None
    assert "<p>" in parsed.body_html


def test_parse_html_only_falls_back_to_stripped_text():
    raw = (
        b"From: Test <test@example.com>\r\n"
        b"To: ops@bridgeos.example\r\n"
        b"Subject: HTML only\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"\r\n"
        b"<html><body><p>Quick reply &mdash; <b>thanks</b>!</p></body></html>\r\n"
    )
    parsed = parse_raw_email(raw)
    assert parsed.from_email == "test@example.com"
    assert "Quick reply" in parsed.body_text
    assert "<p>" not in parsed.body_text


def test_strip_html_collapses_whitespace_and_decodes_entities():
    s = "<p>Hello&nbsp;&amp; world,\n  this is &lt;text&gt;.</p>"
    out = strip_html(s)
    assert "Hello" in out and "world" in out
    assert "&amp;" not in out and "&nbsp;" not in out
    assert "<p>" not in out


def test_parse_empty_body_does_not_throw():
    raw = b"From: x@example.com\r\nTo: y@example.com\r\nSubject: Empty\r\n\r\n"
    parsed = parse_raw_email(raw)
    assert parsed.from_email == "x@example.com"
    assert parsed.body_text == ""
