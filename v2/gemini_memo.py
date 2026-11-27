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
읽는 사람이 한눈에 보도록 한 줄에 한 가지만 쓴다. 긴 문장으로 이어 붙이지 마라.

규칙
- 근거에 없는 숫자를 만들거나 계산하지 마라. 숫자는 근거에 적힌 표기 그대로 옮겨라. '%p'는 쓰지 마라.
- 근거의 '• 순결제 ROAS 기준' 줄부터 '• 4) 기획전별' 블록 끝까지는 줄 나눔 · 빈 줄 · '[하락]' '[상승]' 머리 · 'ㄴ' · '*믹스 효과' 표시와 순서를 그대로 두고 옮겨라. 줄을 합치거나 문장으로 풀어 쓰지 마라.
- '[하락]' · '[상승]' 머리 아래에는 한 곳(매체 · BPU · 기획전)에 한 줄. 'ㄴ' 줄은 바로 위 곳의 상세다.
- 4) 기획전별에는 실제 기획전만 둔다. '서비스비용' · 'LFmall' · '배너개별단위AF코드발급'처럼 기획전이 아닌 묶음은 쓰지 마라.
- 근거에 [데이터 점검]이 있을 때만 맨 앞에 '⚠ 데이터 점검:'으로 시작하는 줄을 써라(무엇이 · 언제 · 얼마, 할 일). 없으면 데이터 이야기는 쓰지 마라.
- '■ 기간 · 비용출처' 같은 제목 줄이나 [읽는 법] 설명은 쓰지 마라.
- 목표 대비 · 가입 · 첫구매 · 추이 이야기는 쓰지 마라(근거에 있어도 옮기지 마라).
- 원인은 단정하지 말고 '~로 보임', '(가설)'처럼 써라. 앱 이용자 누적 같은 근거 없는 원인은 쓰지 마라.
- 4) 뒤에 빈 줄 하나, 그다음 마지막 줄에 확인해 볼 것 1~2가지를 '→ 확인: '으로 시작해 한 줄로 써라(기획전이 아닌 묶음은 대상으로 삼지 마라).
- 머리말 · 맺음말 · 마크다운(**, #, -)은 쓰지 마라.

모양 예시 (숫자는 예시일 뿐, 근거 숫자를 써라)
• 순결제 ROAS 기준 — 나쁨: ROAS(순결제) 774% → 617% (△20%)

• 1) 지표별(ROAS = 1/CPC × UV/클릭 × CR(총결제) × 순결제비중 × 객단가(순결제))
[하락] CPC 43%(30원 → 48원), CR(총결제) 27%(0.25% → 0.19%)
[상승] 객단가(순결제) 56%(171,491원 → 321,407원) · 참고 CTR 4.15% → 7.59%

• 2) 매체 × 상품별
[하락]
카카오 비즈보드 19%(ROAS 1,230% → 843% · 광고비 +1.1백만 · 거래액 +4.0백만)
ㄴ하락 요인 CPC 144%(83원 → 468원, 올라서 ROAS 하락)
ㄴ상승 요인 객단가(순결제) 80%(161,271원 → 421,568원)
[상승]
카카오 모먼트 17%(ROAS 653% → – · 광고비 △1.2백만 · 거래액 △4.8백만)
그 외 11곳 합 3% 하락
*믹스 효과: ROAS 20% 하락 = 광고비 비중 이동 몫 19% 상승, 변화의 △91% + 매체 × 상품 자체 ROAS 변화 몫 39% 하락, 변화의 191%
ㄴ비중 이동이 가장 큰 매체: 카카오 모먼트
ㄴ광고비 비중 39.8% → 0.0%, 전년 ROAS 653%(평균 774%보다 낮음) → ROAS 17% 상승

• 3) BPU별
[하락]
e-마케팅 BSU 89%(ROAS – → 367% · 광고비 +3.4백만 · 거래액 +3.9백만)
[상승]
e-영업2 BPU 29%(ROAS 647% → 1,354% · 광고비 +0.5백만 · 거래액 +12.7백만)
그 외 3곳 합 6% 상승

• 4) 기획전별
[하락]
(실제 기획전 한 줄씩)
[상승]
블랙프라이데이 39%(ROAS -17% → – · 광고비 △1.2백만 · 거래액 +0.2백만)

→ 확인: …

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
               'generationConfig': {'temperature': 0.3, 'maxOutputTokens': 3000}}
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
