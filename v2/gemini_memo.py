# -*- coding: utf-8 -*-
"""리뷰 메모 1차 작성 — Gemini (Streamlit 서버에서만 호출, 키는 st.secrets 에만)

- 브라우저(dashboard.html)가 화면 공식 산식으로 계산한 요약 숫자(facts)와 규칙 기반 초안만 보낸다. 원본 로데이터는 보내지 않는다.
- 키: Streamlit Cloud → Settings → Secrets 에 GEMINI_API_KEY = "..." (선택: GEMINI_MODEL = "모델 이름")
- 모델: GEMINI_MODEL 이 없으면 'gemini-flash-lite-latest'(늘 최신 Flash-Lite 를 가리키는 이름).
  그 모델이 없다고(404) 하면 이 키로 쓸 수 있는 모델 목록을 받아 Flash-Lite → Flash 순으로 골라 다시 부른다.
- 키가 없거나 호출이 실패하면 화면은 규칙 기반 초안을 그대로 쓴다.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_MODEL = 'gemini-flash-lite-latest'
BASE = 'https://generativelanguage.googleapis.com/v1beta'
MAX_FACTS = 12_000          # 보내는 근거 글자 수 상한

PROMPT = """너는 LF몰 DA(디스플레이 광고) 성과를 매일 리뷰하는 퍼포먼스 마케터다.
아래 [근거]는 대시보드가 공식 산식으로 계산한 숫자다. 이것만 써서 '요약 시트 리뷰 메모' 1차 초안을 한국어로 써라.

규칙
- 근거에 없는 숫자를 만들거나 계산하지 마라. 숫자는 근거에 적힌 표기 그대로 옮겨라(기여는 소수점 없는 %). '%p'는 쓰지 마라.
- ROAS 기여는 '+' · '△' 기호 대신 근거처럼 '올린 요인 · 올린 곳' / '내린 요인 · 내린 곳'으로 묶고 '22% 상승'처럼 말로 써라. '플러스' · '마이너스' · '효율↑↓'는 쓰지 마라.
- 판단이 좋음이면 올린 쪽을, 나쁨이면 내린 쪽을 먼저, 기여가 큰 순서로 써라(근거의 순서를 지켜라).
- '기여'는 ROAS 변화율을 나눈 값이다. 같은 번호 안에서 올린 쪽 합 − 내린 쪽 합 = 전체 ROAS 변화율이고, 번호끼리(1)~4))는 같은 변화를 다른 기준으로 나눈 것이라 더하지 않는다. 근거의 [읽는 법]은 한 줄로 줄여 판단 바로 아래에 써라.
- 광고비 · 거래액 옆 금액은 비교 기간 대비 늘어난(+) · 줄어든(△) 금액이다. 비교비(%)로 바꿔 말하지 마라.
- 근거에 [데이터 점검]이 있을 때만 맨 앞에 '⚠ 데이터 점검:'으로 시작하는 줄을 써라(무엇이 · 언제 · 얼마, 할 일). 없으면 데이터 이야기는 쓰지 마라.
- 그다음 '■ 기간 · 비용출처' 제목, 이어서 순결제 ROAS 기준 판단(좋음 / 나쁨 / 보합)과 그 숫자.
- 이어서 글머리표('• ')로 이 순서대로, 항목마다 1~2줄: 1) 지표별(올린 요인 · 내린 요인과 각 기여, 값 변화) → 2) 매체 × 상품별(올린 곳 · 내린 곳 · 그 외 합) → 믹스 효과(순결제 ROAS 변화 = 광고비 비중 이동 몫 + 매체 × 상품 자체 ROAS 변화 몫, 변화의 몇 %인지를 쉬운 말로) → 이슈 매체 상세 → 3) BPU별 → 4) 기획전별. 근거에 없는 항목은 건너뛰어라.
- 그 뒤 목표 대비 · 가입 · 첫구매 · 추이에서 눈에 띄는 점을 짧게(있을 때만).
- 원인은 단정하지 말고 '~로 보임', '(가설)'처럼 써라. 앱 이용자 누적 같은 근거 없는 원인은 쓰지 마라.
- 마지막 줄에 확인해 볼 것 1가지를 '→ 확인: '으로 시작해 써라.
- 머리말 · 맺음말 · 마크다운 굵게(**)는 쓰지 마라.

[근거]
"""

Transport = Callable[[str, str, dict, dict | None, float], dict]


class GeminiError(Exception):
    """사용자에게 보여 줄 수 있는 짧은 오류 (code = HTTP 상태, 없으면 0)"""

    def __init__(self, msg: str, code: int = 0):
        super().__init__(msg)
        self.code = code


def load_config(secrets: Mapping[str, Any] | None) -> tuple[str | None, str]:
    def get(k):
        try:
            v = secrets.get(k) if secrets is not None else None
        except Exception:      # secrets.toml 이 아예 없을 때
            v = None
        return str(v).strip() if v else None
    return get('GEMINI_API_KEY'), get('GEMINI_MODEL') or DEFAULT_MODEL


def _transport(method: str, url: str, headers: dict, payload: dict | None, timeout: float) -> dict:
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except HTTPError as e:
        try:
            body = e.read().decode('utf-8', 'replace')
        except Exception:
            body = ''
        if 'API_KEY_INVALID' in body or 'API key not valid' in body:
            raise GeminiError('Gemini 키가 올바르지 않습니다(Streamlit Secrets 의 GEMINI_API_KEY 확인).', e.code) from None
        if e.code == 429:
            raise GeminiError('Gemini 무료 사용 한도를 잠시 넘었습니다. 1분쯤 뒤에 다시 눌러 주세요.', 429) from None
        if e.code in (401, 403):
            raise GeminiError('Gemini 키에 이 기능 권한이 없습니다(AI Studio 에서 키 · 프로젝트 확인).', e.code) from None
        if e.code == 404:
            raise GeminiError('Gemini 모델을 찾지 못했습니다.', 404) from None
        raise GeminiError(f'Gemini 호출 실패(HTTP {e.code}).', e.code) from None
    except (URLError, TimeoutError):
        raise GeminiError('Gemini 에 연결하지 못했습니다(네트워크 · 시간 초과).') from None


def _version(name: str) -> tuple:
    """'gemini-3.1-flash-lite-001' → (3, 1) — 높은 버전을 먼저 고르기 위한 정렬 키"""
    m = re.search(r'gemini-(\d+)(?:\.(\d+))?', name)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)


def pick_model(api_key: str, transport: Transport | None = None) -> str:
    """이 키로 generateContent 를 쓸 수 있는 모델 중 Flash-Lite → Flash 순, 정식(미리보기 · 실험 아님) · 높은 버전 우선"""
    data = (transport or _transport)('GET', f'{BASE}/models?pageSize=200', {'x-goog-api-key': api_key}, None, 15)
    names = [m.get('name', '').split('/')[-1] for m in data.get('models', [])
             if 'generateContent' in (m.get('supportedGenerationMethods') or [])]
    names = [n for n in names if n.startswith('gemini') and not any(x in n for x in ('image', 'tts', 'audio', 'live', 'embedding', 'vision'))]
    for want in ('flash-lite', 'flash'):
        cand = [n for n in names if want in n and (want != 'flash' or 'lite' not in n)]
        stable = [n for n in cand if not any(x in n for x in ('preview', 'exp'))]
        pool = stable or cand
        if pool:
            return sorted(pool, key=lambda n: (_version(n), 'latest' in n, -len(n)), reverse=True)[0]
    if names:
        return sorted(names, key=_version, reverse=True)[0]
    raise GeminiError('이 Gemini 키로 쓸 수 있는 텍스트 모델이 없습니다(AI Studio 에서 키 · 프로젝트 확인).', 404)


def _generate(facts: str, api_key: str, model: str, transport: Transport | None) -> str:
    url = f'{BASE}/models/{model}:generateContent'
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': api_key}
    payload = {'contents': [{'role': 'user', 'parts': [{'text': PROMPT + facts}]}],
               'generationConfig': {'temperature': 0.3, 'maxOutputTokens': 2000}}
    data = (transport or _transport)('POST', url, headers, payload, 30)
    try:
        parts = data['candidates'][0]['content']['parts']
        text = ''.join(p.get('text', '') for p in parts).strip()
    except (KeyError, IndexError, TypeError):
        raise GeminiError('Gemini 응답을 읽지 못했습니다.') from None
    if not text:
        raise GeminiError('Gemini 가 빈 답을 보냈습니다.')
    return text.replace('**', '')


def write_memo(facts: str, api_key: str, model: str = DEFAULT_MODEL,
               transport: Transport | None = None) -> tuple[str, str]:
    """→ (메모 글, 실제로 쓴 모델). 모델이 없으면(404) 쓸 수 있는 모델을 골라 한 번 더 부른다"""
    if not api_key:
        raise GeminiError('Gemini 키가 설정되지 않았습니다.')
    facts = str(facts or '')[:MAX_FACTS]
    try:
        return _generate(facts, api_key, model, transport), model
    except GeminiError as e:
        if e.code != 404:
            raise
    alt = pick_model(api_key, transport)
    if alt == model:
        raise GeminiError(f'Gemini 모델({model})을 쓸 수 없습니다.', 404)
    return _generate(facts, api_key, alt, transport), alt
