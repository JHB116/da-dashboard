"""
캠페인별 일예산 조정 콕핏 (Budget Cockpit)
──────────────────────────────────────────────
목적: 매일 반복하던 "캠페인별 일예산 조정" 판단을 프로그램화해
      Claude 토큰 소모 없이 앱 안에서 끝내기 위한 전용 대시보드.

핵심 아이디어
  - 데이터(로데이터)는 Claude가 아니라 '이 앱'에 올린다 → 토큰 0.
  - 판단 신호를 계산으로 뽑아준다:
      · ROAS 효율 신호   : 최근 ROAS vs 목표 ROAS
      · 예산 소진 신호   : 월예산 대비 소진 페이스(경과일 대비)
  - "때마다 다르게" 보므로 자동 확정이 아니라, 두 신호와
    권장 일예산을 나란히 보여주고 노브(목표 ROAS·민감도·상하한·
    가중치)로 조정하는 '의사결정 콕핏'.

입력
  1) 로데이터(실적) 파일  [필수]  : dashboard.py와 동일 포맷(CSV/xlsx/xlsb)
  2) 현재 일예산 파일     [선택]  : [캠페인, 일예산, 월예산?, 목표ROAS?]
                                    → 없으면 최근 실제 일소진을 기준으로 추천

기존 dashboard.py는 건드리지 않는다(같은 로딩 로직을 최소 복제).
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
import calendar

try:
    import plotly.graph_objects as go
    _HAS_PLOTLY = True
except Exception:
    _HAS_PLOTLY = False


st.set_page_config(
    page_title="캠페인 일예산 조정 콕핏",
    page_icon="🎚️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""<style>
.main .block-container { padding-top: 1.4rem; max-width: 1500px; }
h1 { font-size: 1.5rem !important; font-weight: 700 !important; color: #0F172A !important; }
h2 { font-size: 1.15rem !important; font-weight: 600 !important; color: #1E293B !important; }
hr { margin: 0.7rem 0 !important; border-color: #E2E8F0 !important; }
.kpi { background:#fff; border:1px solid #E2E8F0; border-radius:10px; padding:12px 14px; }
.kpi .lab { font-size:12px; color:#64748B; }
.kpi .val { font-size:1.4rem; font-weight:700; color:#0F172A; }
</style>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════
# 1. 데이터 로딩 (dashboard.py와 동일 포맷 — 최소 복제)
# ═══════════════════════════════════════════════
WEEKLY_COL_MAP = {
    "노출수": "지표_노출수", "클릭수": "지표_클릭수", "비용": "지표_광고비",
    "UV": "지표_UV(전체)", "결제고객수": "지표_순결제고객수", "결제고객수(총)": "지표_총결제고객수",
    "순결제매출": "지표_순결제거래액", "총결제매출": "지표_총결제거래액",
    "가입수": "지표_가입회원", "첫구매수": "지표_순결제고객수(첫구매)", "첫구매": "지표_순결제거래액(첫구매)",
    "신규고객수": "지표_당년신규순결제고객수", "신규거래액": "지표_당년신규순결제거래액",
    "윈백고객수": "지표_순결제고객수(윈백)", "윈백거래액": "지표_순결제거래액(윈백)",
    "비용출처": "구분_비용출처", "캠페인": "구분_캠페인", "하위캠페인": "구분_하위캠페인",
    "AF코드": "구분_AF코드", "AF코드명": "구분_AF코드이름",
}

# 집계 대상 지표
AGG_COLS = [
    "지표_노출수", "지표_클릭수", "지표_광고비",
    "지표_UV(전체)", "지표_순결제고객수", "지표_총결제고객수",
    "지표_순결제거래액", "지표_총결제거래액",
    "지표_순결제고객수(첫구매)", "지표_순결제거래액(첫구매)",
]


def _map_weekly_format(df: pd.DataFrame) -> pd.DataFrame:
    """접두어 없는 원본('금주누적' 스타일)을 표준 스키마로 변환."""
    for c in df.select_dtypes(include="object").columns:
        df[c] = df[c].astype(str).str.strip()
    if "매체명" in df.columns:
        media = df["매체명"].fillna("").astype(str).str.strip()
        if "상품명" in df.columns:
            prod = df["상품명"].fillna("").astype(str).str.strip()
            df["구분_상품"] = prod
            df["구분_매체명"] = [
                m if (not p or p == m) else f"{m} {p}"
                for m, p in zip(media, prod)
            ]
        else:
            df["구분_매체명"] = media
    df = df.rename(columns=WEEKLY_COL_MAP)
    if "구분_비용출처" in df.columns:
        df = df[~df["구분_비용출처"].astype(str).str.strip().isin(["총합계", "", "nan"])]
    return df


def _parse_date_col(s: pd.Series):
    """기간_일자 견고 파싱 (문자열 / 엑셀 시리얼 / YYYYMMDD 대응)."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s

    def _plausible(d):
        if d is None:
            return 0.0
        yrs = d.dt.year
        ok = (yrs >= 2015) & (yrs <= 2100)
        return float(ok.mean()) if len(d) else 0.0

    candidates = [pd.to_datetime(s, errors="coerce")]
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.5:
        candidates.append(pd.to_datetime(num, unit="D", origin="1899-12-30", errors="coerce"))
    txt = s.astype(str).str.replace(r"[^0-9]", "", regex=True)
    if (txt.str.len() == 8).mean() > 0.5:
        candidates.append(pd.to_datetime(txt, format="%Y%m%d", errors="coerce"))
    return max(candidates, key=_plausible)


@st.cache_data(show_spinner=False)
def load_data(file_bytes: bytes, filename: str) -> pd.DataFrame:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        df = None
        for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
                break
            except Exception:
                continue
        if df is None:
            raise ValueError("파일 인코딩을 인식할 수 없습니다.")
    elif ext == "xlsx":
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    elif ext == "xlsb":
        df = pd.read_excel(io.BytesIO(file_bytes), engine="pyxlsb")
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {ext}")

    df.columns = df.columns.str.strip()
    if "지표_광고비" not in df.columns and ("비용" in df.columns or "순결제매출" in df.columns):
        df = _map_weekly_format(df)

    if "기간_일자" not in df.columns:
        raise ValueError("`기간_일자` 컬럼을 찾을 수 없습니다. 로데이터 형식을 확인하세요.")
    df["기간_일자"] = _parse_date_col(df["기간_일자"])
    df = df.dropna(subset=["기간_일자"])

    num_cols = [
        "지표_노출수", "지표_클릭수", "지표_광고비", "지표_UV(전체)",
        "지표_순결제고객수", "지표_총결제고객수",
        "지표_순결제거래액", "지표_총결제거래액",
        "지표_순결제고객수(첫구매)", "지표_순결제거래액(첫구매)",
        "지표_순결제거래액(윈백)",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    defaults = {
        "구분_비용출처": "기타", "구분_채널": "기타", "구분_매체명": "기타",
        "구분_캠페인": "기타", "구분_상품": "", "카테고리": "기타",
    }
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val

    if "지표_순결제거래액" not in df.columns:
        df["지표_순결제거래액"] = (
            df.get("지표_순결제거래액(첫구매)", 0) + df.get("지표_순결제거래액(윈백)", 0)
        )
    for c in AGG_COLS:
        if c not in df.columns:
            df[c] = 0

    df["연도"] = df["기간_일자"].dt.year
    df["월"] = df["기간_일자"].dt.month
    return df


@st.cache_data(show_spinner=False)
def load_budget_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """현재 일예산 파일 파싱. 유연한 컬럼 인식.
    인식 컬럼(별칭 허용):
      캠페인 / campaign               → key
      일예산 / 예산 / daily / budget  → 일예산
      월예산 / 월예산목표 / monthly    → 월예산 (선택)
      목표ROAS / targetroas / roas목표 → 목표ROAS (선택, % 또는 배수)
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        b = None
        for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
            try:
                b = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
                break
            except Exception:
                continue
        if b is None:
            raise ValueError("예산 파일 인코딩을 인식할 수 없습니다.")
    else:
        b = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    b.columns = [str(c).strip() for c in b.columns]

    def _find(cands):
        low = {c.lower().replace(" ", ""): c for c in b.columns}
        for cand in cands:
            key = cand.lower().replace(" ", "")
            for k, orig in low.items():
                if key == k or key in k:
                    return orig
        return None

    c_camp = _find(["캠페인", "campaign"])
    c_daily = _find(["일예산", "daily", "budget", "예산"])
    c_month = _find(["월예산", "monthly"])
    c_troas = _find(["목표roas", "targetroas", "roas목표", "목표 roas"])
    if not c_camp or not c_daily:
        raise ValueError("예산 파일에서 '캠페인'과 '일예산' 컬럼을 찾지 못했습니다.")

    out = pd.DataFrame({"key": b[c_camp].astype(str).str.strip()})
    out["일예산"] = pd.to_numeric(b[c_daily], errors="coerce")
    out["월예산"] = pd.to_numeric(b[c_month], errors="coerce") if c_month else np.nan
    if c_troas:
        tr = pd.to_numeric(b[c_troas], errors="coerce")
        # 값이 대체로 10보다 크면 %(300) 표기로 보고 배수로 변환
        if tr.dropna().gt(10).mean() > 0.5:
            tr = tr / 100.0
        out["목표ROAS"] = tr
    else:
        out["목표ROAS"] = np.nan
    out = out[out["key"] != ""].drop_duplicates(subset="key", keep="last")
    return out


# ═══════════════════════════════════════════════
# 2. 지표/추천 계산
# ═══════════════════════════════════════════════
def _sum_window(df, dim, start, end):
    """[start, end] 기간의 캠페인별 광고비/거래액 합계."""
    m = (df["기간_일자"] >= pd.Timestamp(start)) & (df["기간_일자"] <= pd.Timestamp(end))
    sub = df.loc[m]
    if sub.empty:
        return pd.DataFrame(columns=[dim, "광고비", "거래액", "일수"])
    g = sub.groupby(dim, dropna=False).agg(
        광고비=("지표_광고비", "sum"),
        거래액=("지표_순결제거래액", "sum"),
        일수=("기간_일자", "nunique"),
    ).reset_index()
    return g


def _roas(rev, spend):
    return rev / spend if spend and spend > 0 else np.nan


def _round_to(x, step):
    if pd.isna(x):
        return np.nan
    return float(int(round(x / step)) * step)


def build_recommendation(df, dim, asof, recent_n, budget_df, cfg):
    """캠페인별 신호 + 권장 일예산 계산."""
    asof = pd.Timestamp(asof)
    recent_start = asof - pd.Timedelta(days=recent_n - 1)
    mtd_start = asof.replace(day=1)
    days_in_month = calendar.monthrange(asof.year, asof.month)[1]
    days_elapsed = asof.day
    days_left = max(days_in_month - days_elapsed, 1)
    day_ratio = days_elapsed / days_in_month

    yday = _sum_window(df, dim, asof, asof).set_index(dim)
    recent = _sum_window(df, dim, recent_start, asof).set_index(dim)
    mtd = _sum_window(df, dim, mtd_start, asof).set_index(dim)

    keys = sorted(set(yday.index) | set(recent.index) | set(mtd.index))
    bmap = budget_df.set_index("key") if budget_df is not None else None

    rows = []
    for k in keys:
        y_sp = float(yday["광고비"].get(k, 0.0)) if k in yday.index else 0.0
        y_rv = float(yday["거래액"].get(k, 0.0)) if k in yday.index else 0.0
        r_sp = float(recent["광고비"].get(k, 0.0)) if k in recent.index else 0.0
        r_rv = float(recent["거래액"].get(k, 0.0)) if k in recent.index else 0.0
        r_days = int(recent["일수"].get(k, 0)) if k in recent.index else 0
        m_sp = float(mtd["광고비"].get(k, 0.0)) if k in mtd.index else 0.0
        m_rv = float(mtd["거래액"].get(k, 0.0)) if k in mtd.index else 0.0

        daily_avg = r_sp / recent_n if recent_n else 0.0
        roas_recent = _roas(r_rv, r_sp)
        roas_yday = _roas(y_rv, y_sp)
        roas_mtd = _roas(m_rv, m_sp)

        # 목표 ROAS: 캠페인별 파일값 우선, 없으면 전역
        t_roas = cfg["target_roas"]
        cur_budget = np.nan
        month_budget = np.nan
        if bmap is not None and k in bmap.index:
            row = bmap.loc[k]
            cur_budget = float(row["일예산"]) if pd.notna(row.get("일예산")) else np.nan
            month_budget = float(row["월예산"]) if pd.notna(row.get("월예산")) else np.nan
            if pd.notna(row.get("목표ROAS")):
                t_roas = float(row["목표ROAS"])

        base = cur_budget if pd.notna(cur_budget) and cur_budget > 0 else daily_avg

        # ── 신호 1: ROAS 효율
        m_roas_mult = 1.0
        roas_ratio = np.nan
        if pd.notna(roas_recent) and t_roas and t_roas > 0:
            roas_ratio = roas_recent / t_roas
            # 밴드 밖일 때만 반응
            if roas_ratio >= 1 + cfg["band"]:
                m_roas_mult = 1 + cfg["sensitivity"] * (roas_ratio - 1)
            elif roas_ratio <= 1 - cfg["band"]:
                m_roas_mult = 1 + cfg["sensitivity"] * (roas_ratio - 1)
            m_roas_mult = float(np.clip(m_roas_mult, 1 - cfg["max_change"], 1 + cfg["max_change"]))
        cand_roas = base * m_roas_mult if base > 0 else np.nan

        # ── 신호 2: 예산 소진 페이스 (월예산 있을 때만)
        pace_index = np.nan
        spend_ratio = np.nan
        proj_eom = np.nan
        remain = np.nan
        cand_pace = np.nan
        rec_daily_budget = np.nan
        if pd.notna(month_budget) and month_budget > 0:
            spend_ratio = m_sp / month_budget
            pace_index = spend_ratio / day_ratio if day_ratio > 0 else np.nan
            proj_eom = (m_sp / days_elapsed * days_in_month) if days_elapsed else np.nan
            remain = month_budget - m_sp
            rec_daily_budget = max(remain, 0) / days_left
            cand_pace = rec_daily_budget

        # ── 결합
        w_roas = cfg["w_roas"]
        w_pace = cfg["w_pace"]
        if pd.notna(cand_roas) and pd.notna(cand_pace):
            tot = w_roas + w_pace
            recommended = (w_roas * cand_roas + w_pace * cand_pace) / tot if tot else cand_roas
        elif pd.notna(cand_roas):
            recommended = cand_roas
        elif pd.notna(cand_pace):
            recommended = cand_pace
        else:
            recommended = np.nan

        # 상하한 & 변화폭 제한 & 반올림
        note_flags = []
        if pd.notna(recommended) and base > 0:
            lo = base * (1 - cfg["max_change"])
            hi = base * (1 + cfg["max_change"])
            recommended = float(np.clip(recommended, lo, hi))
        if pd.notna(recommended):
            if cfg["min_budget"] > 0:
                recommended = max(recommended, cfg["min_budget"])
            if cfg["max_budget"] > 0:
                recommended = min(recommended, cfg["max_budget"])
            recommended = _round_to(recommended, cfg["round_step"])

        delta = recommended - base if (pd.notna(recommended) and base > 0) else np.nan
        pct = (delta / base) if (pd.notna(delta) and base > 0) else np.nan

        # 액션 판정
        if base <= 0 or pd.isna(recommended):
            action = "데이터부족"
        elif pd.notna(pct) and pct > cfg["action_thr"]:
            action = "증액"
        elif pd.notna(pct) and pct < -cfg["action_thr"]:
            action = "감액"
        else:
            action = "유지"

        # 사유 문자열
        reasons = []
        if pd.notna(roas_ratio):
            eff = "효율↑" if roas_ratio >= 1 + cfg["band"] else ("효율↓" if roas_ratio <= 1 - cfg["band"] else "효율≈목표")
            reasons.append(f"ROAS {roas_recent*100:.0f}% vs 목표 {t_roas*100:.0f}% ({eff})")
        if pd.notna(pace_index):
            pc = "느림" if pace_index < 0.95 else ("빠름" if pace_index > 1.05 else "정상")
            reasons.append(f"소진 페이스 {pace_index:.2f}x ({pc})")
        reason = " · ".join(reasons) if reasons else "신호 없음"

        rows.append({
            "캠페인": k,
            "액션": action,
            "어제광고비": y_sp,
            "어제ROAS": roas_yday,
            f"최근{recent_n}일광고비": r_sp,
            f"최근{recent_n}일ROAS": roas_recent,
            "일평균광고비": daily_avg,
            "목표ROAS": t_roas,
            "MTD광고비": m_sp,
            "MTD ROAS": roas_mtd,
            "월예산": month_budget,
            "소진율": spend_ratio,
            "페이스지수": pace_index,
            "월말예상소진": proj_eom,
            "잔여예산": remain,
            "현재일예산": cur_budget,
            "권장일예산": recommended,
            "변화액": delta,
            "변화율": pct,
            "사유": reason,
        })

    res = pd.DataFrame(rows)
    return res, dict(days_in_month=days_in_month, days_elapsed=days_elapsed,
                     days_left=days_left, day_ratio=day_ratio,
                     recent_start=recent_start, mtd_start=mtd_start)


# ═══════════════════════════════════════════════
# 3. 표시 유틸
# ═══════════════════════════════════════════════
def _won(x):
    return "–" if pd.isna(x) else f"{x:,.0f}"


def _pct(x):
    return "–" if pd.isna(x) else f"{x*100:,.0f}%"


def _pct1(x):
    return "–" if pd.isna(x) else f"{x*100:+.1f}%"


def kpi_card(col, label, value):
    col.markdown(f"<div class='kpi'><div class='lab'>{label}</div>"
                 f"<div class='val'>{value}</div></div>", unsafe_allow_html=True)


def style_table(df, recent_n):
    money_cols = ["어제광고비", f"최근{recent_n}일광고비", "일평균광고비", "MTD광고비",
                  "월예산", "월말예상소진", "잔여예산", "현재일예산", "권장일예산", "변화액"]
    roas_cols = ["어제ROAS", f"최근{recent_n}일ROAS", "목표ROAS", "MTD ROAS"]
    pct_cols = ["소진율"]
    fmt = {}
    for c in money_cols:
        if c in df.columns:
            fmt[c] = _won
    for c in roas_cols:
        if c in df.columns:
            fmt[c] = _pct
    for c in pct_cols:
        if c in df.columns:
            fmt[c] = _pct
    if "변화율" in df.columns:
        fmt["변화율"] = _pct1
    if "페이스지수" in df.columns:
        fmt["페이스지수"] = lambda x: "–" if pd.isna(x) else f"{x:.2f}x"

    def _row_style(row):
        color = {"증액": "#DCFCE7", "감액": "#FEE2E2", "유지": "#F1F5F9",
                 "데이터부족": "#FEF9C3"}.get(row["액션"], "")
        return [f"background-color:{color}"] * len(row)

    sty = df.style.format(fmt).apply(_row_style, axis=1)
    return sty


# ═══════════════════════════════════════════════
# 4. 메인
# ═══════════════════════════════════════════════
def main():
    st.title("🎚️ 캠페인별 일예산 조정 콕핏")
    st.caption("데이터는 이 앱에 올리면 계산으로 신호를 뽑아줍니다 — Claude 토큰 소모 없이 매일 판단.")

    # ── 사이드바: 업로드
    with st.sidebar:
        st.subheader("📁 파일 업로드")
        up = st.file_uploader("① 로데이터(실적) *필수", type=["csv", "xlsx", "xlsb"],
                              key="rodata")
        budget_up = st.file_uploader("② 현재 일예산 파일 (선택)", type=["csv", "xlsx"],
                                     key="budget",
                                     help="컬럼: 캠페인 / 일예산 [/ 월예산 / 목표ROAS] — 없으면 최근 실제 일소진으로 추천")

    if up is None:
        st.info("👈 왼쪽에서 **로데이터(실적) 파일**을 올려주세요. (dashboard.py와 같은 형식)")
        st.markdown("""
        #### 이 앱이 하는 일
        1. 캠페인별로 **어제 / 최근 N일 / 이번달(MTD)** 광고비·ROAS를 계산
        2. **ROAS 효율 신호**(최근 ROAS vs 목표)와 **예산 소진 페이스 신호**(월예산 대비)를 나란히 표시
        3. 노브(목표 ROAS·민감도·상하한·가중치)를 돌려 **권장 일예산**과 **증액/감액/유지** 제안
        4. 결과를 **CSV로 다운로드** → 광고 시스템에 그대로 반영

        #### 선택: 현재 일예산 파일
        `캠페인, 일예산` (+선택 `월예산`, `목표ROAS`) 컬럼이면 됩니다.
        - **월예산**이 있으면 소진 페이스 신호가 켜집니다.
        - 없으면 최근 실제 일소진을 기준(base)으로 ROAS 신호만으로 추천합니다.
        """)
        return

    try:
        df = load_data(up.read(), up.name)
    except Exception as e:
        st.error(f"로데이터를 읽지 못했습니다: {e}")
        return

    budget_df = None
    if budget_up is not None:
        try:
            budget_df = load_budget_file(budget_up.read(), budget_up.name)
        except Exception as e:
            st.warning(f"예산 파일을 읽지 못했습니다(무시하고 진행): {e}")

    dmin, dmax = df["기간_일자"].min().date(), df["기간_일자"].max().date()
    st.sidebar.caption(f"데이터 {len(df):,}행 · {dmin} ~ {dmax}")
    if budget_df is not None:
        has_mb = budget_df["월예산"].notna().any()
        st.sidebar.success(f"예산 파일 {len(budget_df)}건 로드"
                           + (" · 월예산 O(페이스 신호 ON)" if has_mb else " · 월예산 X"))

    # ── 조정 노브
    st.sidebar.divider()
    st.sidebar.subheader("🎛️ 조정 노브")
    dims = [c for c in ["구분_캠페인", "구분_매체명", "구분_상품", "구분_비용출처"] if c in df.columns]
    dim_label = st.sidebar.selectbox("집계 단위", dims, index=0)
    asof = st.sidebar.date_input("기준일(어제)", value=dmax, min_value=dmin, max_value=dmax)
    recent_n = st.sidebar.slider("최근 N일 창", 3, 28, 7, step=1)
    target_roas_pct = st.sidebar.slider("목표 ROAS (%)", 50, 1500, 300, step=10,
                                        help="파일에 캠페인별 목표ROAS가 있으면 그 값이 우선합니다.")
    with st.sidebar.expander("고급 설정", expanded=False):
        band_pct = st.slider("무반응 밴드 (±%)", 0, 30, 10, step=1,
                             help="목표 대비 이 범위 안이면 ROAS 신호는 '유지'")
        sensitivity = st.slider("민감도", 0.1, 2.0, 0.6, step=0.1,
                                help="신호를 예산 변화로 얼마나 강하게 반영할지")
        max_change_pct = st.slider("1회 최대 변화폭 (±%)", 5, 100, 30, step=5)
        w_roas = st.slider("가중치: ROAS 효율", 0.0, 1.0, 0.5, step=0.1)
        w_pace = st.slider("가중치: 예산 페이스", 0.0, 1.0, 0.5, step=0.1)
        action_thr_pct = st.slider("액션 임계 (±%)", 1, 30, 5, step=1,
                                   help="변화율이 이보다 작으면 '유지'")
        min_budget = st.number_input("일예산 하한 (원, 0=없음)", min_value=0, value=0, step=10000)
        max_budget = st.number_input("일예산 상한 (원, 0=없음)", min_value=0, value=0, step=10000)
        round_step = st.selectbox("반올림 단위 (원)", [1000, 5000, 10000, 50000], index=0)

    cfg = dict(
        target_roas=target_roas_pct / 100.0,
        band=band_pct / 100.0,
        sensitivity=sensitivity,
        max_change=max_change_pct / 100.0,
        w_roas=w_roas, w_pace=w_pace,
        action_thr=action_thr_pct / 100.0,
        min_budget=min_budget, max_budget=max_budget, round_step=round_step,
    )

    res, meta = build_recommendation(df, dim_label, asof, recent_n, budget_df, cfg)
    if res.empty:
        st.warning("기준일 부근에 해당 단위의 데이터가 없습니다. 기준일/집계 단위를 확인하세요.")
        return

    # ── 요약 KPI
    st.markdown(f"#### 📌 요약 · 기준일 {pd.Timestamp(asof).date()} "
                f"(경과 {meta['days_elapsed']}/{meta['days_in_month']}일, "
                f"최근 {recent_n}일 {meta['recent_start'].date()}~{pd.Timestamp(asof).date()})")
    n_up = int((res["액션"] == "증액").sum())
    n_dn = int((res["액션"] == "감액").sum())
    n_keep = int((res["액션"] == "유지").sum())
    tot_cur = res["현재일예산"].sum(skipna=True)
    tot_rec = res["권장일예산"].sum(skipna=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    kpi_card(c1, "캠페인 수", f"{len(res):,}")
    kpi_card(c2, "🟢 증액", f"{n_up}")
    kpi_card(c3, "🔴 감액", f"{n_dn}")
    kpi_card(c4, "⚪ 유지", f"{n_keep}")
    base_label = "현재→권장 일예산 합" if res["현재일예산"].notna().any() else "권장 일예산 합"
    delta_txt = ""
    if res["현재일예산"].notna().any() and tot_cur > 0:
        delta_txt = f"  ({(tot_rec/tot_cur-1)*100:+.1f}%)"
    kpi_card(c5, base_label, f"{_won(tot_rec)}{delta_txt}")

    # ── 필터
    st.divider()
    fc1, fc2, fc3 = st.columns([1.2, 1.2, 2])
    act_filter = fc1.multiselect("액션 필터", ["증액", "감액", "유지", "데이터부족"],
                                 default=["증액", "감액"])
    sort_by = fc2.selectbox("정렬 기준",
                            ["변화액(절대값)", "변화율", f"최근{recent_n}일광고비", "MTD광고비",
                             f"최근{recent_n}일ROAS", "페이스지수"], index=0)
    search = fc3.text_input("캠페인 검색", "")

    view = res.copy()
    if act_filter:
        view = view[view["액션"].isin(act_filter)]
    if search.strip():
        view = view[view["캠페인"].astype(str).str.contains(search.strip(), case=False, na=False)]
    if sort_by == "변화액(절대값)":
        view = view.reindex(view["변화액"].abs().sort_values(ascending=False, na_position="last").index)
    else:
        col = f"최근{recent_n}일ROAS" if sort_by == f"최근{recent_n}일ROAS" else sort_by
        view = view.sort_values(col, ascending=False, na_position="last")

    # ── 컬럼 순서
    order = ["캠페인", "액션", "현재일예산", "권장일예산", "변화액", "변화율",
             "어제광고비", "어제ROAS", f"최근{recent_n}일광고비", f"최근{recent_n}일ROAS",
             "일평균광고비", "목표ROAS", "MTD광고비", "MTD ROAS",
             "월예산", "소진율", "페이스지수", "월말예상소진", "잔여예산", "사유"]
    order = [c for c in order if c in view.columns]
    view = view[order]

    st.markdown(f"#### 📋 캠페인별 조정 제안 ({len(view)}개)")
    st.dataframe(style_table(view, recent_n), use_container_width=True,
                 hide_index=True, height=560)

    # ── 다운로드
    csv = view.copy()
    st.download_button(
        "📄 조정안 CSV 다운로드",
        data=csv.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"budget_adjust_{pd.Timestamp(asof).date()}.csv",
        mime="text/csv",
    )

    # ── Top movers 차트
    if _HAS_PLOTLY:
        movers = res.dropna(subset=["변화액"]).copy()
        movers = movers.reindex(movers["변화액"].abs().sort_values(ascending=False).index).head(15)
        if not movers.empty:
            movers = movers.iloc[::-1]
            colors = ["#16A34A" if v >= 0 else "#DC2626" for v in movers["변화액"]]
            fig = go.Figure(go.Bar(
                x=movers["변화액"], y=movers["캠페인"], orientation="h",
                marker_color=colors,
                text=[f"{v:+,.0f}" for v in movers["변화액"]], textposition="outside",
            ))
            fig.update_layout(
                title="변화액 Top 15 (증액=초록 / 감액=빨강)",
                height=460, margin=dict(l=10, r=40, t=40, b=10),
                xaxis_title="일예산 변화(원)", plot_bgcolor="white",
            )
            st.plotly_chart(fig, use_container_width=True)

    with st.expander("ℹ️ 계산 방식 / 신호 설명", expanded=False):
        st.markdown(f"""
        - **base(기준 예산)**: 현재 일예산 파일값 → 없으면 최근 {recent_n}일 **일평균 광고비**.
        - **ROAS 신호**: 최근 {recent_n}일 ROAS ÷ 목표 ROAS.
          목표 대비 ±{band_pct if 'band_pct' in dir() else cfg['band']*100:.0f}% 밴드 밖일 때만 반응(민감도 반영).
        - **예산 페이스 신호**(월예산 필요): 소진율 ÷ 경과일비율 = 페이스지수.
          `>1` 빠름(감액 압력), `<1` 느림(증액 여력). 잔여예산÷남은일 = 페이스 기준 권장 일소진.
        - **결합**: 두 신호를 가중 평균(ROAS {cfg['w_roas']:.1f} : 페이스 {cfg['w_pace']:.1f}),
          1회 최대 변화폭 ±{cfg['max_change']*100:.0f}%·상하한·반올림 적용.
        - **액션**: 변화율 {cfg['action_thr']*100:.0f}% 초과 시 증액/감액, 그 안이면 유지.
        - **최종 판단은 사람이**: 이 표는 신호 정리용입니다. 노브를 돌려 그날 관점(ROAS 중심 / 페이스 중심)에 맞게 보세요.
        """)


if st.runtime.exists():
    main()
