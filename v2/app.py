# -*- coding: utf-8 -*-
"""DA 광고 실적 대시보드 v2 — Streamlit 배포용 (Main file path: v2/app.py)

dashboard.html 을 화면 가득 띄운다. 실적 데이터는 저장소에도 서버에도 없다.
- 원천은 PC 에서 make_backup.bat(매일) · make_backup_24.bat(24년, 처음 한 번) · make_targets.bat(목표 파일)로 백업(.json.gz)을 만들어
  화면에 끌어다 놓는다 → 이 브라우저(IndexedDB)에 날짜 단위로 합쳐 저장. 서버는 원천을 받지 않아 메모리가 거의 들지 않는다.
- 리뷰 메모 1차 초안: Gemini 키(Streamlit Secrets 의 GEMINI_API_KEY)가 있으면 서버가 Gemini 로 쓰고, 없으면 화면의 규칙 기반 초안.
  Gemini 에는 화면이 계산한 요약 숫자만 보낸다.
기존 대시보드(저장소 루트 dashboard.py)와는 따로 배포한다.
"""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import gemini_memo as gm

ROOT = Path(__file__).resolve().parent
MARKER = '<script src="calc.js"></script>'
DASHBOARD = components.declare_component('da_dashboard_v2', path=str(ROOT / 'streamlit_component'))

st.set_page_config(page_title='DA 광고 실적 대시보드', page_icon='📊', layout='wide', initial_sidebar_state='collapsed')
st.markdown(
    """<style>
    header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], footer {display: none !important;}
    .block-container, [data-testid="stMainBlockContainer"] {padding: 0 !important; max-width: 100% !important;}
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {overflow: hidden !important;}
    [data-testid="stVerticalBlock"] {gap: 0 !important;}
    [data-testid="stMainBlockContainer"], [data-testid="stVerticalBlock"], [data-testid="stElementContainer"]:has(iframe) {height: 100vh !important; height: 100dvh !important;}
    iframe {display: block; width: 100% !important; height: 100vh !important; height: 100dvh !important; border: 0;}
    </style>""",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def page(stamp):
    """dashboard.html + calc.js 를 한 장으로 — stamp(수정시각)가 바뀌면 다시 읽는다"""
    html = (ROOT / 'dashboard.html').read_text(encoding='utf-8')
    calc = (ROOT / 'calc.js').read_text(encoding='utf-8')
    if MARKER not in html:
        raise RuntimeError('dashboard.html 에서 calc.js 를 넣을 자리를 찾지 못했습니다')
    return html.replace(MARKER, f'<script>\n{calc}\n</script>', 1)


api_key, model = gm.load_config(st.secrets)
stamp = tuple((ROOT / f).stat().st_mtime for f in ('dashboard.html', 'calc.js'))
request = DASHBOARD(
    html=page(stamp), pageStamp='|'.join(map(str, stamp)),
    gemini={'configured': bool(api_key), 'model': model},
    memoResponse=st.session_state.get('memo_response'),
    key='da-dashboard-v2', default=None,
)
if isinstance(request, dict) and request.get('type') == 'gemini_memo' and request.get('id'):
    rid = str(request['id'])[:100]
    if rid != st.session_state.get('memo_last_id'):
        try:
            text = gm.write_memo(request.get('facts', ''), api_key, model=model)
            resp = {'id': rid, 'key': request.get('key'), 'ok': True, 'text': text}
        except gm.GeminiError as e:
            resp = {'id': rid, 'key': request.get('key'), 'ok': False, 'message': str(e)}
        st.session_state['memo_last_id'] = rid
        st.session_state['memo_response'] = resp
        st.rerun()
