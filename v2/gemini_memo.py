# -*- coding: utf-8 -*-
"""리뷰 메모 1차 작성 — Gemini (Streamlit 서버에서만 호출, 키는 st.secrets 에만)

- 브라우저(dashboard.html)가 화면 공식 산식으로 계산한 요약 숫자(facts)와 규칙 기반 초안만 보낸다. 원본 로데이터는 보내지 않는다.
- 키: Streamlit Cloud → Settings → Secrets 에 GEMINI_API_KEY = "..." (선택: GEMINI_MODEL = "gemini-2.5-flash-lite")
- 키가 없거나 호출이 실패하면 화면은 규칙 기반 초안을 그대로 쓴다.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_MODEL = 'gemini-2.5-flash-lite'
MAX_FACTS = 12_000          # 보내는 근거 글자 수 상한

PROMPT = """너는 LF몰 DA(디스플레이 광고) 성과를 매일 리뷰하는 퍼포먼스 마케터다.
아래 [근거]는 대시보드가 공식 산식으로 계산한 숫자다. 이것만 써서 '요약 시트 리뷰 메모' 1차 초안을 한국어로 써라.

규칙
- 근거에 없는 숫자를 만들거나 계산하지 마라. 숫자는 근거에 적힌 표기(백만원 · % · %p · △)를 그대로 옮겨라.
- 5~8개의 글머리표('• ')로, 한 줄에 한 가지만. 첫 줄은 '■ 기간 · 비용출처' 제목.
- 순서: 핵심 실적(광고비 · 거래액 · ROAS, 전년 · 전전년 비교) → 목표 대비(있을 때) → 효율 변화의 이유 → 매체별 증감 → 가입 · 첫구매(있을 때) → 추이에서 눈에 띄는 점.
- 원인은 단정하지 말고 '~로 보임', '(가설)'처럼 써라. 앱 이용자 누적 같은 근거 없는 원인은 쓰지 마라.
- 마지막 줄에 확인해 볼 것 1가지를 '→ 확인: '으로 시작해 써라.
- 머리말 · 맺음말 · 마크다운 굵게(**)는 쓰지 마라.

[근거]
"""


class GeminiError(Exception):
    """사용자에게 보여 줄 수 있는 짧은 오류"""


def load_config(secrets: Mapping[str, Any] | None) -> tuple[str | None, str]:
    def get(k):
        try:
            v = secrets.get(k) if secrets is not None else None
        except Exception:      # secrets.toml 이 아예 없을 때
            v = None
        return str(v).strip() if v else None
    return get('GEMINI_API_KEY'), get('GEMINI_MODEL') or DEFAULT_MODEL


def _transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    req = Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except HTTPError as e:
        try:
            body = e.read().decode('utf-8', 'replace')
        except Exception:
            body = ''
        if 'API_KEY_INVALID' in body or 'API key not valid' in body:
            raise GeminiError('Gemini 키가 올바르지 않습니다(Streamlit Secrets 의 GEMINI_API_KEY 확인).') from None
        if e.code == 429:
            raise GeminiError('Gemini 무료 사용 한도를 잠시 넘었습니다. 1분쯤 뒤에 다시 눌러 주세요.') from None
        if e.code in (401, 403):
            raise GeminiError('Gemini 키가 올바르지 않습니다(Streamlit Secrets 의 GEMINI_API_KEY 확인).') from None
        raise GeminiError(f'Gemini 호출 실패(HTTP {e.code}).') from None
    except (URLError, TimeoutError):
        raise GeminiError('Gemini 에 연결하지 못했습니다(네트워크 · 시간 초과).') from None


def write_memo(facts: str, api_key: str, model: str = DEFAULT_MODEL,
               transport: Callable[[str, dict, dict, float], dict] | None = None) -> str:
    if not api_key:
        raise GeminiError('Gemini 키가 설정되지 않았습니다.')
    facts = str(facts or '')[:MAX_FACTS]
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': api_key}
    payload = {'contents': [{'role': 'user', 'parts': [{'text': PROMPT + facts}]}],
               'generationConfig': {'temperature': 0.3, 'maxOutputTokens': 1200}}
    data = (transport or _transport)(url, headers, payload, 30)
    try:
        parts = data['candidates'][0]['content']['parts']
        text = ''.join(p.get('text', '') for p in parts).strip()
    except (KeyError, IndexError, TypeError):
        raise GeminiError('Gemini 응답을 읽지 못했습니다.') from None
    if not text:
        raise GeminiError('Gemini 가 빈 답을 보냈습니다.')
    return text.replace('**', '')
