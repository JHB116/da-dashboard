# da-dashboard
lf da dashboard

## 앱 구성

| 파일 | 실행 | 용도 |
| --- | --- | --- |
| `dashboard.py` | `streamlit run dashboard.py` | DA 광고 실적 대시보드(요약·매체·캠페인·전년비 등) |
| `budget_dashboard.py` | `streamlit run budget_dashboard.py` | **캠페인별 일예산 조정 콕핏** (신규) |

## 캠페인별 일예산 조정 콕핏 (`budget_dashboard.py`)

매일 반복하던 "캠페인별 일예산 조정" 판단을 **앱 안에서 계산으로** 끝내
Claude 토큰 소모 없이 처리하기 위한 전용 대시보드.

- **입력**
  1. 로데이터(실적) 파일 — `dashboard.py`와 동일 포맷(CSV/xlsx/xlsb) *필수*
  2. 현재 일예산 파일 — `캠페인, 일예산` (+선택 `월예산`, `목표ROAS`) *선택*
- **신호 2종**
  - ROAS 효율: 최근 N일 ROAS vs 목표 ROAS
  - 예산 소진 페이스: 월예산 대비 소진율 ÷ 경과일비율 (월예산 있을 때)
- **출력**: 캠페인별 증액/감액/유지 제안 + 권장 일예산 → CSV 다운로드
- 노브(목표 ROAS·민감도·상하한·가중치)로 그날 관점에 맞게 조정. 최종 판단은 사람이.

### 로컬 실행
```bash
pip install -r requirements.txt
streamlit run budget_dashboard.py
```

### Streamlit Cloud 배포
같은 저장소에서 **메인 파일을 `budget_dashboard.py`로 지정**해 별도 앱으로 추가하면 됩니다.
