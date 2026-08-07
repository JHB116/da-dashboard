# -*- coding: utf-8 -*-
"""
DA 카피 분석·제안
─────────────────────────────────────────────────────────────
DA 디스플레이 광고 '소재(카피+이미지)'와 '실적'을 소재 단위로 조인해,
어떤 소구형·카피·이미지속성이 성과(CTR·ROAS·RPS)를 만드는지와 다음 제안을 도출한다.

── 데이터 모델 (실제 검증됨) ───────────────────────────────
  · 소재안(기획측): 주차별 Drive 엑셀(비즈보드/디스플레이/버즈빌 …).
      한 기획전(기획전번호) 안에서 소재가 등장 순서대로 1,2,3… 번호를 가진다.
      컬럼: 기획전번호·기획전명·브랜드·카테고리·성별·이미지유형·소구형(수동)·메인카피·서브카피 …
      ⚠️ 수동 '소구형'은 사람이 단 라벨이라 부정확 → 카피 원문/이미지 기준으로 재분류한다.
  · 실적(성과측): DA로우_RAW (25~26년 누적). 소재별 성과는
      구분_AF코드이름 = 'M카카오비즈보드_{기획전}(ADID[/앵커링])_{N}' 의 끝 _{N} 으로 식별.
      → (구분_기획전 번호, 소재순서 N) 이 소재안과의 조인 키.
      같은 소재 N 이 매체 변형(ADID / ADID앵커링)으로 여러 행이면 합산한다.
  · 조인: (기획전번호, 소재N)  →  소재의 {카피·소구형·이미지속성} ↔ {노출·클릭·거래액·ROAS}

── 설계 원칙 (발송 대시보드 계승) ──────────────────────────
  · 순수 함수(load_da_perf / parse_creative_order / tag_copy / appeal_perf …) = Streamlit 무관·테스트 가능.
  · 단일 하루는 소재별 전환이 희소(거래액 0 다수) → 분석은 '기간 누적' 위에서 해야 안정적.
"""
import io
import re
import numpy as np
import pandas as pd

# ══════════════════════════════════════════════════════════════════════
# 0-A. 소재안(주차별 Drive 엑셀) → 소재 단위 카피/속성
# ══════════════════════════════════════════════════════════════════════
# 소재안 시트 컬럼 인덱스(0-based, 헤더 3행). 실측 확인됨.
SOJAE_COLS = {
    "기획전번호": 10, "기획전명": 11, "상품명": 13, "이미지유형": 14,
    "브랜드": 16, "소구형_수동": 17, "메인카피": 18, "서브카피": 20,
    "성별": 4, "카테고리": 8, "최종소재안": 31,
}


def parse_sojae_bytes(file_bytes, sheet=None, header_row=3):
    """소재안 엑셀 bytes → 소재 단위 DataFrame.
    한 기획전번호 그룹 안에서 등장 순서대로 소재N(1,2,3…)을 매긴다(실적 _N 과 대칭)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
    recs, cur_pid, n = [], None, 0
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        def cell(key):
            i = SOJAE_COLS[key]
            v = row[i] if i < len(row) else None
            return "" if v is None else str(v).replace("\n", " ").strip()
        pid = cell("기획전번호")
        if not pid:
            continue
        if pid != cur_pid:
            cur_pid, n = pid, 0
        n += 1
        recs.append({
            "기획전번호": pid, "소재N": n, "기획전명": cell("기획전명"),
            "브랜드": cell("브랜드"), "카테고리": cell("카테고리"), "성별": cell("성별"),
            "이미지유형": cell("이미지유형"), "소구형_수동": cell("소구형_수동"),
            "메인카피": cell("메인카피"), "서브카피": cell("서브카피"),
        })
    wb.close()
    df = pd.DataFrame(recs)
    if not df.empty:
        df["기획전번호"] = pd.to_numeric(df["기획전번호"], errors="coerce").astype("Int64")
        df["소재N"] = df["소재N"].astype("Int64")
    return df


# ══════════════════════════════════════════════════════════════════════
# 0-B. 실적(DA로우_RAW) → 소재별 성과
# ══════════════════════════════════════════════════════════════════════
# 매체 프리셋: 소재안 폴더(비즈보드/디스플레이/버즈빌)와 대응. AF코드이름 안의 매체 토큰으로 식별.
MEDIA_TOKENS = {"비즈보드": "비즈보드", "버즈빌": "버즈빌", "디스플레이": "디스플레이"}

PERF_NUM = ["지표_노출수", "지표_클릭수", "지표_광고비", "지표_순결제거래액",
            "지표_순결제고객수", "지표_UV(전체)", "지표_총결제거래액", "지표_순결제고객수(첫구매)"]

# 성과 주지표: 라벨 → (분자, 분모, 클수록 좋은가)
METRICS = {
    "ROAS":   ("지표_순결제거래액", "지표_광고비",   True),
    "CTR":    ("지표_클릭수",       "지표_노출수",   True),
    "RPS(노출당)": ("지표_순결제거래액", "지표_노출수", True),
    "CR(순)": ("지표_순결제고객수",  "지표_UV(전체)", True),
    "CPC(낮을수록↑)": ("지표_광고비", "지표_클릭수",  False),
}


def parse_creative_order(af_name):
    """구분_AF코드이름 끝의 _{N} → 소재순서(int) 또는 NA."""
    m = re.search(r"_(\d+)\s*$", str(af_name))
    return int(m.group(1)) if m else pd.NA


def load_da_perf(raw_df, media="비즈보드"):
    """DA로우_RAW → (기획전번호, 소재N) 단위 소재별 성과 집계.
    같은 소재의 매체변형(ADID/앵커링) 행은 합산한다."""
    df = raw_df.copy()
    name = df["구분_AF코드이름"].astype(str)
    if media and media in MEDIA_TOKENS:
        df = df[name.str.contains(MEDIA_TOKENS[media], na=False)].copy()
    df["소재N"] = df["구분_AF코드이름"].map(parse_creative_order).astype("Int64")
    df["기획전번호"] = pd.to_numeric(df["구분_기획전 번호"], errors="coerce").astype("Int64")
    for c in PERF_NUM:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    keys = ["기획전번호", "소재N"]
    nm = df.groupby(keys, dropna=False)["구분_브랜드/기획전"].first()
    agg = df.groupby(keys, dropna=False)[[c for c in PERF_NUM if c in df.columns]].sum()
    out = agg.join(nm.rename("기획전명")).reset_index()
    return out


def load_da_perf_bytes(file_bytes, media="비즈보드", sheet="DA로우_RAW"):
    """대용량 DA로우 엑셀 bytes → (기획전번호, 소재N) 소재별 성과. openpyxl 스트리밍 집계
    (45MB 전체 누적도 pandas 전체 로드 없이 메모리 효율적으로 처리)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb[sheet] if sheet in wb.sheetnames else wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    header = [("" if h is None else str(h).strip()) for h in next(it)]
    idx = {}
    for i, h in enumerate(header):
        idx.setdefault(h, i)
    af_i, pid_i = idx.get("구분_AF코드이름"), idx.get("구분_기획전 번호")
    br_i = idx.get("구분_브랜드/기획전")
    met_i = {c: idx[c] for c in PERF_NUM if c in idx}
    tok = MEDIA_TOKENS.get(media)
    agg, names = {}, {}
    for row in it:
        name = row[af_i] if af_i is not None and af_i < len(row) else None
        if not name:
            continue
        name = str(name)
        if tok and tok not in name:
            continue
        m = re.search(r"_(\d+)\s*$", name)
        if not m:
            continue
        N = int(m.group(1))
        pv = row[pid_i] if pid_i is not None and pid_i < len(row) else None
        try:
            pid = int(float(pv))
        except (TypeError, ValueError):
            continue
        key = (pid, N)
        d = agg.setdefault(key, {c: 0.0 for c in met_i})
        for c, i in met_i.items():
            v = row[i] if i < len(row) else None
            try:
                d[c] += float(v)
            except (TypeError, ValueError):
                pass
        if key not in names and br_i is not None and br_i < len(row) and row[br_i]:
            names[key] = str(row[br_i])
    wb.close()
    rows = [{"기획전번호": k[0], "소재N": k[1], "기획전명": names.get(k, ""), **v}
            for k, v in agg.items()]
    df = pd.DataFrame(rows)
    if not df.empty:
        df["기획전번호"] = df["기획전번호"].astype("Int64")
        df["소재N"] = df["소재N"].astype("Int64")
    return df


def _rate(n, d):
    d = pd.to_numeric(d, errors="coerce")
    return np.where(d > 0, pd.to_numeric(n, errors="coerce") / d, np.nan)


def add_perf_kpis(perf):
    """소재별 성과에 CTR/ROAS/RPS/CR 파생 추가."""
    p = perf.copy()
    p["CTR"]  = _rate(p["지표_클릭수"], p["지표_노출수"])
    p["ROAS"] = _rate(p["지표_순결제거래액"], p["지표_광고비"])
    p["RPS"]  = _rate(p["지표_순결제거래액"], p["지표_노출수"])
    p["CR"]   = _rate(p["지표_순결제고객수"], p["지표_UV(전체)"])
    return p


# ══════════════════════════════════════════════════════════════════════
# 1. 소재안 카피 → 소구형 태깅  (수동 라벨 대신 카피/이미지 기준 재분류)
#    택소노미는 LF 실사용(할인/혜택/인기/공감/상품/브랜드)에 신상/시즌/한정 등을 보강.
# ══════════════════════════════════════════════════════════════════════
DA_KW = {
    "할인율": ["할인", "세일", "오프", "OFF", "off", "%", "％", "반값", "특가", "핫딜"],
    "가격": ["최저가", "단돈", "균일가", "가성비", "무료배송", "무배", "원부터", "인하"],
    "쿠폰": ["쿠폰", "적립", "페이백", "캐시백", "포인트", "플러스쿠폰", "즉시할인"],
    "혜택": ["혜택", "이벤트", "찬스", "기회", "최대혜택", "특별"],
    "인기": ["인기", "베스트", "BEST", "Best", "1위", "랭킹", "TOP", "완판", "품절대란", "많이 팔린", "사랑받"],
    "공감": ["그만", "이제", "고민", "말고", "안 입", "필수템", "이 가격에", "어떻게", "라운딩"],
    "신상": ["신상", "신규", "출시", "입고", "재입고", "론칭", "컬렉션", "NEW", "new", "드롭"],
    "시즌": ["여름", "겨울", "봄", "가을", "환절기", "시즌", "썸머", "윈터", "연말", "휴가", "필드", "라운딩"],
    "단독": ["단독", "독점", "한정", "선착순", "리미티드", "LF몰 단독", "온라인 단독"],
    "브랜드소구": ["브랜드", "공식", "데상트", "르꼬끄", "헤지스", "닥스", "질스튜어트", "킨", "바네사브루노"],
    "상품소구": ["티셔츠", "팬츠", "셔츠", "니트", "원피스", "스니커즈", "샌들", "블라우스", "의류", "잡화", "골프화"],
}
KW_RE = {k: re.compile("|".join(re.escape(w) for w in ws)) for k, ws in DA_KW.items()}
PCT_RE   = re.compile(r"\d{1,3}\s*[%％]")
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
TAG_BOOLS = list(DA_KW.keys()) + ["질문형", "이모지"]


def _s(v):
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def tag_copy(main_copy, sub_copy=""):
    """메인+서브 카피 → 소구형 dict. (이미지 OCR 카피를 넣으면 더 정확)"""
    t = (_s(main_copy) + " " + _s(sub_copy)).strip()
    d = {k: bool(KW_RE[k].search(t)) for k in DA_KW}
    d["할인율"] = d["할인율"] or bool(PCT_RE.search(t))
    d["질문형"] = ("?" in t or "？" in t)
    d["이모지"] = bool(EMOJI_RE.search(t))
    return d


def add_tags(sojae_df, main_col="메인카피", sub_col="서브카피"):
    """소재안 DataFrame 에 소구형 태그(bool) 컬럼 추가."""
    df = sojae_df.copy()
    mains = df[main_col] if main_col in df else ""
    subs  = df[sub_col] if sub_col in df else ""
    tags = pd.DataFrame([tag_copy(m, s) for m, s in zip(
        (mains if hasattr(mains, "__iter__") else [""]*len(df)),
        (subs if hasattr(subs, "__iter__") else [""]*len(df)))], index=df.index)
    return pd.concat([df, tags], axis=1)


# ══════════════════════════════════════════════════════════════════════
# 2. 조인: 소재안(카피·소구형·이미지속성) ↔ 실적(성과)
# ══════════════════════════════════════════════════════════════════════
def join_sojae_perf(sojae_df, perf_df, pid_col="기획전번호", order_col="소재N"):
    """(기획전번호, 소재N) 기준 조인. 소재안=왼쪽(카피/속성), 실적=오른쪽(성과)."""
    s = sojae_df.copy()
    s[pid_col] = pd.to_numeric(s[pid_col], errors="coerce").astype("Int64")
    s[order_col] = pd.to_numeric(s[order_col], errors="coerce").astype("Int64")
    return s.merge(perf_df, on=[pid_col, order_col], how="inner", suffixes=("", "_실적"))


# ══════════════════════════════════════════════════════════════════════
# 3. 소구형/이미지속성별 성과 + 유의성  (발송 대시보드 통계층 이식)
# ══════════════════════════════════════════════════════════════════════
def _welch_p(a, b):
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
    sp = np.sqrt(((len(a)-1)*a.var(ddof=1) + (len(b)-1)*b.var(ddof=1)) / (len(a)+len(b)-2))
    return (a.mean() - b.mean()) / sp if sp else np.nan


def fdr_bh(pvals):
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx); out = [None]*len(pvals)
    if not m:
        return out
    prev = 1.0
    for rank, i in enumerate(sorted(idx, key=lambda i: pvals[i], reverse=True), 1):
        prev = min(prev, pvals[i] * m / (m - rank + 1)); out[i] = prev
    return out


def appeal_perf(joined, metric_label, tags=None, min_n=5):
    """소구형(또는 임의 bool 태그)별 '보유 vs 미보유' 가중성과 + 유의성."""
    num, den, higher = METRICS[metric_label]
    tags = tags or [t for t in TAG_BOOLS if t in joined.columns]
    per_row = pd.Series(_rate(joined[num], joined[den]), index=joined.index)
    rows, pv = [], []
    for tag in tags:
        has = joined[tag].fillna(False).astype(bool)
        nh, nn = int(has.sum()), int((~has).sum())
        if nh < min_n or nn < min_n:
            continue
        wh = _rate(joined.loc[has, num].sum(), joined.loc[has, den].sum())
        wn = _rate(joined.loc[~has, num].sum(), joined.loc[~has, den].sum())
        p = _welch_p(per_row[has].values, per_row[~has].values)
        rows.append({"태그": tag, "보유가중": float(wh), "보유n": nh, "미보유가중": float(wn),
                     "미보유n": nn, "차이": float(wh)-float(wn),
                     "효과크기": _cohen_d(per_row[has].values, per_row[~has].values), "p": p})
        pv.append(p)
    for r, q in zip(rows, fdr_bh(pv)):
        r["q"] = q
    out = pd.DataFrame(rows)
    return out.sort_values("차이", ascending=not higher).reset_index(drop=True) if len(out) else out


def cat_perf(joined, cat_col, metric_label, min_n=3):
    """범주형 컬럼(이미지유형·브랜드·소구형_수동 등) 값별 가중 성과."""
    num, den, higher = METRICS[metric_label]
    rows = []
    for val, sub in joined.groupby(cat_col):
        if not str(val).strip() or len(sub) < min_n:
            continue
        rows.append({cat_col: str(val), "n": len(sub),
                     metric_label: float(_rate(sub[num].sum(), sub[den].sum())),
                     "노출": float(pd.to_numeric(sub["지표_노출수"], errors="coerce").sum())})
    out = pd.DataFrame(rows)
    return out.sort_values(metric_label, ascending=not higher).reset_index(drop=True) if len(out) else out


def sig_label(q):
    if q is None or (isinstance(q, float) and pd.isna(q)):
        return "표본부족"
    if q < 0.01: return "p<0.01 · 신뢰가능"
    if q < 0.05: return "p<0.05 · 유의함"
    if q < 0.10: return "p<0.10 · 약한신호"
    return f"q={q:.2f} · 유의하지않음"


# ══════════════════════════════════════════════════════════════════════
# 4. Streamlit UI (개요) — 조인된 소재×성과 위에서 렌더
# ══════════════════════════════════════════════════════════════════════
def render(sojae_df, raw_perf_df, media="비즈보드"):
    import streamlit as st
    st.title("📝 DA 카피 분석·제안")
    if sojae_df is None or raw_perf_df is None:
        st.info("소재안(카피)과 실적(DA로우)을 모두 올리면 소재별로 조인해 분석해요.")
        return
    perf = add_perf_kpis(load_da_perf(raw_perf_df, media=media))
    tagged = add_tags(sojae_df)
    joined = join_sojae_perf(tagged, perf)
    st.caption(f"조인된 소재 {len(joined):,}건 · 매체: {media}")
    metric = st.selectbox("성과 주지표", list(METRICS), index=0)
    ap = appeal_perf(joined, metric)
    if ap.empty:
        st.warning("표본이 부족해요. 기간을 넓히거나 매체를 바꿔보세요."); return
    st.dataframe(ap, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    import sys
    # 실적 로더 스모크 테스트: 실제 DA로우 파일 경로를 인자로 주면 소재별 성과를 출력
    if len(sys.argv) > 1:
        raw = pd.read_excel(sys.argv[1], sheet_name="DA로우_RAW", header=0, engine="openpyxl")
        perf = add_perf_kpis(load_da_perf(raw, media="비즈보드"))
        print("소재행:", len(perf), "· 기획전:", perf["기획전번호"].nunique())
        top = perf[perf["지표_노출수"] > 3000].copy()
        top["CTR%"] = (top["CTR"]*100).round(2); top["ROAS%"] = (top["ROAS"]*100).round(0)
        print(top.sort_values("지표_노출수", ascending=False)
              [["기획전번호", "기획전명", "소재N", "지표_노출수", "지표_클릭수", "CTR%", "ROAS%"]].head(12).to_string(index=False))
    else:
        # 태깅 스모크 테스트
        print("tags:", tag_copy("데상트&르꼬끄 여름골프 ~60%", "단독특가 시원한 라운딩!"))
