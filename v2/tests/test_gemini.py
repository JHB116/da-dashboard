# -*- coding: utf-8 -*-
"""gemini_memo — 키 · 요청 모양 · 응답 읽기 · 오류 변환 (실제 호출 없이 가짜 transport)"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gemini_memo as gm  # noqa: E402


def test_write_memo_request_and_parse():
    seen = {}

    def fake(url, headers, payload, timeout):
        seen.update(url=url, headers=headers, payload=payload)
        return {'candidates': [{'content': {'parts': [{'text': '■ 26년 10월\n• **광고비** 268.5백만원'}]}}]}
    out = gm.write_memo('광고비 268.5백만원 (+23.4%)', 'KEY', model='m1', transport=fake)
    assert out.startswith('■') and '**' not in out
    assert seen['url'].endswith('/models/m1:generateContent') and seen['headers']['x-goog-api-key'] == 'KEY'
    assert '광고비 268.5백만원 (+23.4%)' in seen['payload']['contents'][0]['parts'][0]['text']


def test_errors():
    with pytest.raises(gm.GeminiError):
        gm.write_memo('x', '', transport=lambda *a: {})
    with pytest.raises(gm.GeminiError):
        gm.write_memo('x', 'K', transport=lambda *a: {'candidates': []})


def test_config():
    assert gm.load_config({}) == (None, gm.DEFAULT_MODEL)
    assert gm.load_config({'GEMINI_API_KEY': ' k ', 'GEMINI_MODEL': 'x'}) == ('k', 'x')
