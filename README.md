# da-dashboard
lf da dashboard

- `dashboard.py` — 기존 DA 대시보드 (Streamlit, Main file path `dashboard.py`)
- `v2/` — 새 DA 대시보드(정적 HTML + 브라우저 저장, 24년 파일 한 번만 업로드). 옮기는 중이며 기존과 숫자 비교용으로 함께 쓴다 → [`v2/README.md`](v2/README.md)

## 분석 메모 · Gemini 초안 (기존 `dashboard.py`)

전체 요약 · 커스텀 그래프의 **📝 분석 메모**에서 **🤖 Gemini 초안**을 누르면 Gemini 가 1차 초안을 써서 편집창에 넣는다(확인 · 수정 후 **💾 저장**해야 남는다). v2 와 같은 `v2/gemini_memo.py` 를 쓴다.

1. [Google AI Studio](https://aistudio.google.com/apikey) 에서 API 키 발급(무료 등급).
2. Streamlit Cloud → 기존 대시보드 앱 → **Settings → Secrets** 에 `GEMINI_API_KEY = "발급받은 키"` (선택: `GEMINI_MODEL = "모델 이름"`). v2 앱과 따로 배포했다면 이 앱에도 넣어야 한다. 키가 없으면 버튼이 꺼져 있다.
3. Gemini 에는 화면이 계산한 요약 숫자만 보낸다 — 기간 합계(전년 · 전전년 동요일 / 비교 기간 대비), 비용출처 · 매체별 상위, 기간 · 일별 추이. 원본 로데이터는 보내지 않는다. 무료 등급은 Google 이 보낸 내용을 서비스 개선에 쓸 수 있으니 사내 기준을 확인할 것.
