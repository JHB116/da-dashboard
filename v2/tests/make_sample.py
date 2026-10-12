# -*- coding: utf-8 -*-
"""테스트용 가짜 DA 로데이터(실제 수치 아님) — 기존 dashboard.py 와 같은 컬럼 형식

python tests/make_sample.py OUT_DIR
  → OUT_DIR/sample_24.csv      (2024-01-01 ~ 2025-01-31 · 24년 파일 역할, 2025년 1월이 섞여 있어 잘림 확인용)
  → OUT_DIR/sample_2526.csv    (2024-12-01 ~ 2026-10-10 · 매일 파일 역할, 2024년 12월이 섞여 있어 고정 구간 확인용)
  → OUT_DIR/sample_1011.csv    (2026-10-05 ~ 2026-10-11 · 다음 날 파일, 겹치는 날짜는 값이 다름)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MEDIA = [('카카오', '비즈보드', '포탈'), ('카카오', '디스플레이', '포탈'), ('네이버', 'GFA', '포탈'),
         ('FB/IG', '전환', 'SNS'), ('구글', 'GDN', 'SNS'), ('토스', '토스애즈', '생활밀착형앱'), ('버즈빌', '허니스크린', '생활밀착형앱')]
SRCS = ['거래액확대', '신규고객확대', '인지도제고', '서비스비용-거래액확대', 'E영업/광고주직접정산', '기타출처']
BPU = ['e-영업1 BPU', 'e-영업2 BPU', 'e-영업3 BPU', '마케팅']
CATS = ['여성', '남성', '잡화', '통합']
DEVS = ['MO', 'PC', 'APP']


def make(start, end, seed, bump=1.0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq='D')
    rows = []
    for d in dates:
        for mi, (md, pr, ch) in enumerate(MEDIA):
            for si, src in enumerate(SRCS):
                if (mi + si + d.dayofyear) % 3 == 0:
                    continue
                for dev in DEVS[: 1 + (mi % 3)]:
                    camp = f'{md}_{src[:2]}_캠페인{(d.month + mi) % 4}'
                    cost = float(rng.integers(20_000, 900_000)) * bump
                    imp = int(cost / rng.uniform(2, 8))
                    clk = int(imp * rng.uniform(0.002, 0.03))
                    uv = int(clk * rng.uniform(0.5, 0.95))
                    tpay = int(uv * rng.uniform(0.002, 0.03))
                    npay = int(tpay * rng.uniform(0.7, 1))
                    fp = int(npay * rng.uniform(0, 0.4))
                    join = int(uv * rng.uniform(0, 0.02))
                    nrev_fp = fp * rng.integers(30_000, 90_000)
                    wb = npay - fp
                    nrev_wb = wb * rng.integers(30_000, 90_000)
                    rows.append({
                        '기간_일자': d.strftime('%Y-%m-%d'), '구분_광고유형': 'DA', '대상여부': '대상' if si != 5 else '비대상',
                        '구분_채널': ch, '구분_매체명': f'{md} {pr}', '구분_상품': pr, '구분_비용출처': src,
                        '구분_캠페인': camp, '구분_하위캠페인': f'{camp}_sub{d.day % 3}', '구분_부서명': BPU[(mi + si) % 4],
                        '카테고리': CATS[(mi * 3 + si) % 4], '구분_디바이스': dev, '구분_기획전 번호': 114000 + (d.month * 7 + mi) % 50,
                        '구분_브랜드/기획전': f'기획전{(d.month + si) % 5}', '구분_AF코드': f'AF{mi}{si}{d.day}', '구분_AF코드이름': f'소재{mi}{si}',
                        '구분_키워드(소재)': f'BU_A_기획_혜택_2A_통합_{mi}',
                        '지표_노출수': imp, '지표_클릭수': clk, '지표_광고비': cost, '지표_UV(전체)': uv,
                        '지표_UV(회원)': int(uv * 0.6), '지표_PV(회원)': int(uv * 2.1), '지표_가입회원': join,
                        '지표_총결제고객수(첫구매)': fp + 1, '지표_순결제고객수': npay, '지표_총결제거래액(첫구매)': nrev_fp * 1.1,
                        '지표_총결제거래액': (nrev_fp + nrev_wb) * 1.15, '지표_순결제거래액': nrev_fp + nrev_wb,
                        '지표_당년신규순결제고객수': int(fp * 0.8), '지표_당년신규순결제거래액': nrev_fp * 0.8,
                        '지표_총결제고객수': tpay, '지표_순결제고객수(첫구매)': fp, '지표_순결제거래액(첫구매)': nrev_fp,
                        '지표_순결제고객수(윈백)': wb, '지표_순결제거래액(윈백)': nrev_wb,
                        '지표_총결제고객수(윈백)': wb + 1, '지표_총결제거래액(윈백)': nrev_wb * 1.1, '지표_영상조회수': 0,
                    })
    return pd.DataFrame(rows)


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    make('2024-01-01', '2025-01-31', 1).to_csv(out / 'sample_24.csv', index=False, encoding='utf-8-sig')
    make('2024-12-01', '2026-10-10', 2).to_csv(out / 'sample_2526.csv', index=False, encoding='utf-8-sig')
    make('2026-10-05', '2026-10-11', 3, bump=1.3).to_csv(out / 'sample_1011.csv', index=False, encoding='cp949')
    print('ok', out)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'data/sample')
