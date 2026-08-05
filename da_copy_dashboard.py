# -*- coding: utf-8 -*-
"""
DA 카피 분석·제안 (스캐폴드 · 1차안)
─────────────────────────────────────────────────────────────
DA 디스플레이 광고 소재의 '카피 원문'에서 소구형을 규칙 기반으로 직접 태깅하고,
소구형별 성과(가중)·유의성·순효과를 뽑아 "어떤 카피가 왜 이기는가 + 다음 제안"을 도출한다.

설계 원칙 (발송 대시보드 계승):
  · 데이터 로직(tag_copy / add_tags / appeal_perf 등)은 Streamlit 비의존 순수 함수 → import만으로 테스트.
  · UI 는 render(df) 안에 있고, 기존 dashboard.py 의 로데이터(df)를 그대로 받아 재파싱 없이 사용.
  · 지표는 기존 지표_ 원자료를 '가중 집계'(합/합)로 계산 → per-소재 KPI 단순평균의 왜곡 방지.

⚠️ DRAFT 로 표시된 부분(소구형 사전 DA_KW / 기본 카피 컬럼)은 실제 데이터 확인 후 함께 확정.
"""
import re
import numpy as np
import pandas as pd

# ══════════════════════════════════════════════════════════════════════
# 0. 설정 — 실제 데이터 확인 후 조정할 지점
# ══════════════════════════════════════════════════════════════════════

# 카피 원문이 담긴 컬럼 후보 (앞에서부터 존재하는 첫 컬럼을 기본값으로). UI에서 변경 가능.
# DRAFT: 실적 로데이터에 자유텍스트 카피가 어디에 있는지 확정되면 맨 앞으로 옮길 것.
COPY_COL_CANDIDATES = ["구분_AF코드이름", "구분_캠페인", "구분_하위캠페인", "구분_상품"]

# 성과 주지표: 표시라벨 → (분자컬럼, 분모컬럼, 값이 클수록 좋은가)
# 전부 기존 지표_ 원자료 기반 가중비율이라 스케일이 정확하다.
METRICS = {
    "순결제ROAS":  ("지표_순결제거래액",            "지표_광고비",        True),
    "CTR":         ("지표_클릭수",                  "지표_노출수",        True),
    "CR(순)":      ("지표_순결제고객수",            "지표_UV(전체)",      True),
    "첫구매율":    ("지표_순결제고객수(첫구매)",     "지표_UV(전체)",      True),
    "CPC(낮을수록↑)": ("지표_광고비",               "지표_클릭수",        False),
}

# ══════════════════════════════════════════════════════════════════════
# 1. 소구형 태깅 사전 (DRAFT) — DA 디스플레이 광고 맥락에 맞춘 1차 초안
#    발송(CRM) KW는 쿠폰·적립·마감임박 등 메시지형이라, DA용으로 재구성했다.
# ══════════════════════════════════════════════════════════════════════
DA_KW = {
    "할인율소구":   ["할인", "세일", "반값", "오프", "OFF", "off", "%", "％", "균일", "특가할인"],
    "가격소구":     ["특가", "최저가", "단돈", "균일가", "초특가", "가성비", "무료배송", "무배",
                    "배송비", "원부터", "만원", "9,900", "19,900", "인하"],
    "쿠폰적립":     ["쿠폰", "적립", "페이백", "캐시백", "포인트", "마일리지", "즉시할인", "카드"],
    "브랜드소구":   ["브랜드", "공식", "단독", "브랜드데이", "브랜드위크", "정식", "오리지널", "flagship"],
    "신상출시":     ["신상", "신규", "출시", "입고", "재입고", "론칭", "런칭", "발매", "신제품",
                    "컬렉션", "룩북", "NEW", "new", "New", "드롭", "예약판매", "S/S", "F/W"],
    "베스트인기":   ["베스트", "BEST", "Best", "랭킹", "TOP", "1위", "인기", "완판", "품절대란",
                    "화제", "스테디", "밀리언"],
    "후기신뢰":     ["후기", "리뷰", "재구매", "만족", "평점", "추천템", "검증", "실착"],
    "한정희소":     ["한정", "단독", "선착순", "수량", "품절임박", "리미티드", "한정판", "독점",
                    "소진", "조기", "마지막"],
    "시즌시의성":   ["여름", "겨울", "봄", "가을", "환절기", "간절기", "시즌", "서머", "윈터",
                    "연말", "신년", "새해", "명절", "휴가", "바캉스", "장마", "한파"],
    "추천큐레이션": ["추천", "큐레이션", "엄선", "MD", "코디", "스타일링", "PICK", "Pick", "픽",
                    "제안", "셋업", "가이드", "어울리"],
    "사은품증정":   ["증정", "사은품", "기프트", "1+1", "더블", "덤", "추가증정", "선물", "받아가"],
    "혜택포괄":     ["혜택", "이벤트", "특별", "찬스", "기회", "혜자", "럭키"],
    "신규유치":     ["첫구매", "첫 구매", "신규가입", "가입", "웰컴", "회원가입", "신규회원", "첫 주문"],
    "개인화타겟":   ["회원님", "고객님", "님,", "님!", "님 ", "맞춤", "VIP", "등급", "전용", "멤버십"],
    "행동유도":     ["지금", "바로", "click", "클릭", "확인", "담기", "구매하기", "만나보", "놓치지"],
}
KW_RE = {k: re.compile("|".join(re.escape(w) for w in ws)) for k, ws in DA_KW.items()}
PCT_RE   = re.compile(r"\d{1,3}\s*[%％]")
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")

TAG_BOOLS = list(DA_KW.keys()) + ["질문형", "이모지"]


def _s(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v)


def tag_copy(text):
    """카피 원문 → 소구형 속성 dict (bool). 분석의 핵심 축."""
    t = _s(text).strip()
    d = {k: bool(KW_RE[k].search(t)) for k in DA_KW}
    d["할인율소구"] = d["할인율소구"] or bool(PCT_RE.search(t))
    d["질문형"] = ("?" in t or "？" in t)
    d["이모지"] = bool(EMOJI_RE.search(t))
    d["_카피"] = t
    d["_카피길이"] = len(t)
    return d


def add_tags(df, copy_col):
    """df 에 소구형 태그 컬럼(bool)을 붙인다. copy_col = 카피 원문 컬럼명."""
    if df is None or df.empty or copy_col not in df.columns:
        out = df.copy() if df is not None else pd.DataFrame()
        for k in TAG_BOOLS:
            out[k] = False
        return out
    tags = df[copy_col].map(tag_copy).apply(pd.Series)
    out = pd.concat([df.reset_index(drop=True), tags.reset_index(drop=True)], axis=1)
    return out


def resolve_copy_col(df):
    """존재하는 카피 컬럼 후보 중 첫 번째를 반환 (없으면 None)."""
    for c in COPY_COL_CANDIDATES:
        if c in df.columns:
            return c
    return None


# ══════════════════════════════════════════════════════════════════════
# 2. 성과·유의성 통계 (순수 함수)
# ══════════════════════════════════════════════════════════════════════
def _wratio(sub, num, den):
    """가중비율 = 합(분자)/합(분모). 분모 0이면 NaN."""
    n = pd.to_numeric(sub.get(num), errors="coerce").sum()
    d = pd.to_numeric(sub.get(den), errors="coerce").sum()
    return (n / d) if d else np.nan


def _per_row_metric(df, num, den):
    """소재별 지표값 배열 (유의성 검정용). 분모 0/결측은 제외."""
    n = pd.to_numeric(df.get(num), errors="coerce")
    d = pd.to_numeric(df.get(den), errors="coerce")
    m = np.where((d > 0), n / d, np.nan)
    return pd.Series(m, index=df.index)


def _welch_p(a, b):
    """Welch t-test p값. scipy 없으면 None."""
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    b = np.asarray(b, float); b = b[~np.isnan(b)]
    if len(a) < 3 or len(b) < 3:
        return None
    try:
        from scipy import stats
        return float(stats.ttest_ind(a, b, equal_var=False).pvalue)
    except Exception:
        return None


def _cohen_d(a, b):
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    b = np.asarray(b, float); b = b[~np.isnan(b)]
    if len(a) < 2 or len(b) < 2:
        return np.nan
    va, vb = a.var(ddof=1), b.var(ddof=1)
    sp = np.sqrt(((len(a)-1)*va + (len(b)-1)*vb) / (len(a)+len(b)-2))
    return (a.mean() - b.mean()) / sp if sp else np.nan


def fdr_bh(pvals):
    """Benjamini-Hochberg 보정 q값. None은 그대로 통과."""
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx)
    out = [None] * len(pvals)
    if m == 0:
        return out
    order = sorted(idx, key=lambda i: pvals[i])
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):
        k = m - rank + 1
        q = min(prev, pvals[i] * m / k)
        out[i] = q
        prev = q
    return out


def appeal_perf(df, metric_label, min_n=5):
    """소구형별 '보유 vs 미보유' 가중성과 + 유의성.
    반환: DataFrame(소구형, 보유평균, 보유n, 미보유평균, 미보유n, 차이, 효과크기, p, q)."""
    if metric_label not in METRICS:
        raise ValueError(f"unknown metric: {metric_label}")
    num, den, higher_better = METRICS[metric_label]
    rows, pvals = [], []
    per_row = _per_row_metric(df, num, den)
    for tag in DA_KW:
        if tag not in df.columns:
            continue
        has = df[tag].fillna(False).astype(bool)
        n_has, n_not = int(has.sum()), int((~has).sum())
        if n_has < min_n or n_not < min_n:
            continue
        w_has = _wratio(df[has], num, den)
        w_not = _wratio(df[~has], num, den)
        a = per_row[has].values
        b = per_row[~has].values
        p = _welch_p(a, b)
        rows.append({
            "소구형": tag, "보유평균": w_has, "보유n": n_has,
            "미보유평균": w_not, "미보유n": n_not,
            "차이": (w_has - w_not) if (pd.notna(w_has) and pd.notna(w_not)) else np.nan,
            "효과크기": _cohen_d(a, b), "p": p,
        })
        pvals.append(p)
    qs = fdr_bh(pvals)
    for r, q in zip(rows, qs):
        r["q"] = q
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("차이", ascending=not higher_better).reset_index(drop=True)
    return out


def sig_label(q):
    if q is None or (isinstance(q, float) and np.isnan(q)):
        return "표본부족"
    if q < 0.01:  return "p<0.01 · 신뢰 가능"
    if q < 0.05:  return "p<0.05 · 유의함"
    if q < 0.10:  return "p<0.10 · 약한 신호"
    return f"q={q:.2f} · 유의하지 않음"


# ══════════════════════════════════════════════════════════════════════
# 3. Streamlit UI  (기존 dashboard.py 의 로데이터 df 를 받아 렌더)
# ══════════════════════════════════════════════════════════════════════
def render(df):
    import streamlit as st
    import plotly.graph_objects as go

    st.title("📝 DA 카피 분석·제안")
    st.caption("소재 카피 원문에서 소구형을 직접 태깅해, 어떤 소구가 성과를 만드는지와 다음 제안을 도출합니다. "
               "(소재 키워드 코드 대신 카피 원문 기준)")

    if df is None or df.empty:
        st.info("먼저 실적 로데이터를 업로드하세요.")
        return

    # 카피 컬럼 선택
    text_cols = [c for c in COPY_COL_CANDIDATES if c in df.columns] or \
                [c for c in df.columns if df[c].dtype == object]
    default_idx = 0
    copy_col = st.selectbox("카피 원문 컬럼", text_cols, index=default_idx,
                            help="소구형 태깅에 사용할 자유텍스트 컬럼")
    metric_label = st.selectbox("성과 주지표", list(METRICS), index=0)
    min_n = st.number_input("최소 표본(소재 수)", min_value=3, max_value=100, value=5, step=1)

    tagged = add_tags(df, copy_col)

    # 태깅 커버리지
    n_total = len(tagged)
    n_tagged = int(tagged[list(DA_KW)].any(axis=1).sum())
    st.caption(f"소재 {n_total:,}건 · 소구형 1개 이상 태깅된 소재 {n_tagged:,}건 "
               f"({n_tagged/n_total*100:.0f}%) · 카피컬럼: `{copy_col}`")

    perf = appeal_perf(tagged, metric_label, min_n=int(min_n))
    if perf.empty:
        st.warning("표본이 부족합니다. 최소 표본을 낮추거나 카피 컬럼을 바꿔보세요.")
        return

    # 발산형 막대 — 소구형별 (보유-미보유) 차이
    higher_better = METRICS[metric_label][2]
    is_pct = metric_label != "순결제ROAS" and not metric_label.startswith("CPC")
    fig = go.Figure()
    diff = perf["차이"]
    colors = ["#48bb78" if (v >= 0) == higher_better else "#f56565" for v in diff.fillna(0)]
    fig.add_trace(go.Bar(y=perf["소구형"], x=diff, orientation="h", marker_color=colors))
    fig.update_layout(height=max(320, 34*len(perf)), margin=dict(l=10, r=10, t=30, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      title=f"{metric_label} — 소구형 보유 시 성과 차이 (보유 − 미보유)")
    st.plotly_chart(fig, use_container_width=True)

    # 표
    def _fmt(v):
        if pd.isna(v): return "–"
        return f"{v*100:.2f}%" if is_pct else f"{v*100:.0f}%" if metric_label == "순결제ROAS" else f"{v:.1f}"
    tbl = perf.copy()
    for c in ["보유평균", "미보유평균", "차이"]:
        tbl[c] = perf[c].map(_fmt)
    tbl["효과크기"] = perf["효과크기"].map(lambda v: "–" if pd.isna(v) else f"{v:+.2f}")
    tbl["유의성"] = perf["q"].map(sig_label)
    st.dataframe(tbl[["소구형", "보유평균", "보유n", "미보유평균", "미보유n", "차이", "효과크기", "유의성"]],
                 use_container_width=True, hide_index=True)
    st.caption("차이 = 해당 소구형을 쓴 소재의 가중 성과 − 안 쓴 소재의 가중 성과. "
               "효과크기(d)·유의성(FDR 보정)으로 우연 여부를 함께 판단하세요.")

    # 제안 (1차) — 유의하게 좋은 소구형 상위
    st.subheader("💡 제안 — 밀어볼 소구형")
    good = perf[(perf["q"].notna()) & (perf["q"] < 0.10)]
    good = good[(good["차이"] > 0) == higher_better]
    if good.empty:
        st.info("아직 통계적으로 뚜렷하게 이기는 소구형이 없어요. 표본이 쌓이면 다시 확인하세요.")
    else:
        for _, r in good.head(5).iterrows():
            st.markdown(f"- **{r['소구형']}** — {metric_label} {_fmt(r['차이'])} 우위 "
                        f"({sig_label(r['q'])}, 소재 {int(r['보유n'])}건)")
        st.caption("다음 소재 기획 시 위 소구형을 우선 반영하고, A/B로 검증하세요.")


if __name__ == "__main__":
    # 순수 함수 스모크 테스트 (Streamlit 없이)
    demo = pd.DataFrame({
        "구분_AF코드이름": ["여름 시즌오프 최대 70% OFF", "신상 컬렉션 단독 출시",
                          "베스트 1위 후기 좋은 그 상품", "쿠폰받고 무료배송", "브랜드데이 단독혜택"],
        "지표_클릭수": [1200, 800, 1500, 900, 1100],
        "지표_노출수": [40000, 35000, 42000, 30000, 38000],
        "지표_광고비": [500000, 400000, 600000, 350000, 480000],
        "지표_순결제거래액": [2500000, 1200000, 3300000, 1500000, 2400000],
        "지표_순결제고객수": [40, 18, 55, 22, 38],
        "지표_UV(전체)": [1100, 700, 1400, 820, 1000],
        "지표_순결제고객수(첫구매)": [12, 6, 20, 8, 11],
    })
    t = add_tags(demo, "구분_AF코드이름")
    print("tagged cols:", [c for c in TAG_BOOLS if c in t.columns][:6])
    print(appeal_perf(t, "순결제ROAS", min_n=1).to_string(index=False))
