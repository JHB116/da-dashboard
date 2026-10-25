/* DA 광고 실적 대시보드 v2 — 공식 산식 (화면과 테스트가 함께 쓴다)
 * 브라우저: window.DaCalc / Node: require('./calc.js')
 * 원칙(기존 dashboard.py 와 같다)
 *  - 비율 · 단가 지표는 기간 합계 ÷ 합계 (일평균의 평균이 아님)
 *  - 일평균 = 기간 합계 ÷ 집행일수(선택 조건에서 데이터가 있는 날짜 수)
 *  - 전년비 = 동요일 기준(-364일), 전전년비 = -728일. 진행 중인 기간은 데이터가 있는 날짜만 비교(MTD)
 */
(function (root) {
  'use strict';

  // ── 지표 ───────────────────────────────────────────────────────────
  // kind: money(원 → 백만원 표기) · won(원 그대로: CPA·CPC) · count(수) · ratio(0~1 → %) · roas(0~ → %)
  const BASE = ['imp', 'clk', 'cost', 'uv', 'uvm', 'pvm', 'join', 'npay', 'tpay', 'nrev', 'trev', 'fp', 'fpr', 'fpt', 'fprt',
    'nb', 'nbr', 'wb', 'wbr', 'wbt', 'wbrt', 'vv', 'rd', 'pp', 'bk', 'sv', 'gd', 'pt', 'sp'];
  const M = (k, n, kind, base, f, o = {}) => ({ k, n, kind, base, f, ...o });
  const METRIC_LIST = [
    M('cost', '광고비', 'money', ['cost'], s => s.cost),
    M('nrev', '거래액(순결제)', 'money', ['nrev'], s => s.nrev),
    M('roas', 'ROAS(순결제)', 'roas', ['nrev', 'cost'], s => div(s.nrev, s.cost)),
    M('npr', '순결제비중', 'ratio', ['npay', 'tpay'], s => div(s.npay, s.tpay), { dp: 1 }),
    M('trev', '거래액(총결제)', 'money', ['trev'], s => s.trev),
    M('troas', 'ROAS(총결제)', 'roas', ['trev', 'cost'], s => div(s.trev, s.cost)),
    M('uv', 'UV', 'count', ['uv'], s => s.uv),
    M('crt', 'CR(총결제)', 'ratio', ['tpay', 'uv'], s => div(s.tpay, s.uv), { dp: 3 }),
    M('crct', 'CR(클릭기준·총결제)', 'ratio', ['tpay', 'clk'], s => div(s.tpay, s.clk), { dp: 3 }),
    M('aovt', '객단가(총결제)', 'won', ['trev', 'tpay'], s => div(s.trev, s.tpay)),
    M('cpc', 'CPC', 'won', ['cost', 'clk'], s => div(s.cost, s.clk), { lowerBetter: true }),
    M('ctr', 'CTR', 'ratio', ['clk', 'imp'], s => div(s.clk, s.imp), { dp: 2 }),
    M('cpuv', 'CPUV', 'won', ['cost', 'uv'], s => div(s.cost, s.uv), { lowerBetter: true }),
    M('join', '가입수', 'count', ['join'], s => s.join),
    M('jcpa', '가입CPA', 'won', ['cost', 'join'], s => div(s.cost, s.join), { lowerBetter: true }),
    M('nbr', '신규거래액', 'money', ['nbr'], s => s.nbr),
    M('fp', '첫구매수', 'count', ['fp'], s => s.fp),
    M('fcpa', '첫구매CPA', 'won', ['cost', 'fp'], s => div(s.cost, s.fp), { lowerBetter: true }),
    M('ncpa', '신규CPA', 'won', ['cost', 'nb'], s => div(s.cost, s.nb), { lowerBetter: true }),
    // 상세 표에만
    M('imp', '노출수', 'count', ['imp'], s => s.imp),
    M('clk', '클릭수', 'count', ['clk'], s => s.clk),
    M('cpm', 'CPM', 'won', ['cost', 'imp'], s => div(s.cost * 1000, s.imp), { lowerBetter: true }),
    M('npay', '결제고객수(순)', 'count', ['npay'], s => s.npay),
    M('crn', 'CR(순결제)', 'ratio', ['npay', 'uv'], s => div(s.npay, s.uv), { dp: 3 }),
    M('aovn', '객단가(순결제)', 'won', ['nrev', 'npay'], s => div(s.nrev, s.npay)),
    M('tpay', '결제고객수(총)', 'count', ['tpay'], s => s.tpay),
    M('uvc', 'UV/클릭', 'ratio', ['uv', 'clk'], s => div(s.uv, s.clk), { dp: 2 }),
    M('jr', '가입률', 'ratio', ['join', 'uv'], s => div(s.join, s.uv), { dp: 3 }),
    M('fpu', '첫구매율', 'ratio', ['fp', 'uv'], s => div(s.fp, s.uv), { dp: 3 }),
    M('fpr', '첫구매거래액', 'money', ['fpr'], s => s.fpr),
    M('fps', '첫구매비중', 'ratio', ['fpr', 'trev'], s => div(s.fpr, s.trev), { dp: 2 }),
    M('nb', '신규고객수', 'count', ['nb'], s => s.nb),
    M('nbs', '신규비중', 'ratio', ['nbr', 'trev'], s => div(s.nbr, s.trev), { dp: 2 }),
    M('wb', '윈백고객수', 'count', ['wb'], s => s.wb),
    M('wbr', '윈백거래액', 'money', ['wbr'], s => s.wbr),
    M('wbs', '윈백비중', 'ratio', ['wbr', 'trev'], s => div(s.wbr, s.trev), { dp: 2 }),
  ];
  const METRIC = Object.fromEntries(METRIC_LIST.map(m => [m.k, m]));
  // 요약 타일 · 추이 차트 (기존 대시보드 전체요약 순서)
  const SUMMARY = ['cost', 'nrev', 'roas', 'npr', 'trev', 'troas', 'uv', 'crt', 'crct', 'aovt', 'cpc', 'ctr', 'cpuv', 'join', 'jcpa', 'nbr', 'fp', 'fcpa', 'ncpa'];
  // 기간별 상세 표 (기존 dashboard.py DAILY_DETAIL_SPEC 순서)
  const DETAIL = ['imp', 'clk', 'ctr', 'crn', 'aovn', 'npay', 'cpm', 'cpc', 'cpuv', 'uv', 'cost', 'nrev', 'roas', 'npr', 'trev', 'troas',
    'uvc', 'crt', 'crct', 'aovt', 'tpay', 'jr', 'join', 'jcpa', 'fpu', 'fp', 'fcpa', 'fpr', 'fps', 'nb', 'ncpa', 'nbr', 'nbs', 'wb', 'wbr'];

  // 비용출처 묶음 — dashboard.py COST_BUCKETS 와 같다 (공백 · 대소문자 · 전각 슬래시 무시하고 비교)
  const COST_BUCKETS = {
    'TOTAL': ['거래액확대', '신규고객확대', '인지도제고', 'E영업/광고주직접정산', '신규고객확대-실적구분', '브랜드비용', '거래액확대-실적구분',
      '서비스비용-정산제외', '브랜드/정산제외', '인지도제고/브랜딩', '서비스비용-e영업', '서비스비용-E영업', '서비스비용-거래액확대',
      '서비스비용-인지도제고', 'E영업/정산제외'],
    'TOTAL(서비스비용미반영)': ['거래액확대', '신규고객확대', '인지도제고', 'E영업/광고주직접정산', '신규고객확대-실적구분', '브랜드비용',
      '거래액확대-실적구분', '브랜드/정산제외', '인지도제고/브랜딩', 'E영업/정산제외'],
    '거래액확대': ['거래액확대', '거래액확대-실적구분', 'E영업/광고주직접정산', 'E영업/정산제외', '서비스비용-거래액확대', '서비스비용-e영업', '서비스비용-E영업'],
    '신규고객확대': ['신규고객확대', '신규고객확대-실적구분'],
    '인지도제고': ['인지도제고', '서비스비용-인지도제고', '인지도제고/브랜딩'],
  };
  const normCost = s => String(s).replace(/[ 　]/g, '').replace(/／/g, '/').toLowerCase();
  function bucketValues(vals, bucket) {
    const set = new Set((COST_BUCKETS[bucket] || []).map(normCost));
    return vals.filter(v => set.has(normCost(v)));
  }

  function div(a, b) { return b ? a / b : null; }
  function pct(a, b) { return (a == null || b == null || !b || !isFinite(a) || !isFinite(b)) ? null : (a - b) / Math.abs(b) * 100; }

  // ── 날짜 ───────────────────────────────────────────────────────────
  const DAY = 864e5;
  function dnum(iso) { return Math.round(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / DAY); }
  function iso(n) { return new Date(n * DAY).toISOString().slice(0, 10); }
  function dow(n) { return new Date(n * DAY).getUTCDay(); } // 0=일
  function monthDays(y, m) { return new Date(Date.UTC(y, m, 0)).getUTCDate(); }
  const WD = ['일', '월', '화', '수', '목', '금', '토'];
  const SHIFT = { yoy: 364, yoy2: 728 };

  // 차트 세로 점선 — 필요하면 추가 ({date, label})
  const EVENTS = [];

  // ── 데이터셋 ───────────────────────────────────────────────────────
  function prepare(sec) {
    const n = sec.n != null ? sec.n : sec.f.d.length;
    const ds = { dates: sec.dates, dn: Int32Array.from(sec.dates.map(dnum)), n, dims: sec.dims, dimKeys: Object.keys(sec.dims), f: {}, byNum: new Map() };
    ds.dates.forEach((d, i) => ds.byNum.set(ds.dn[i], i));
    ds.f.d = Int32Array.from(sec.f.d);
    for (const k of ds.dimKeys) ds.f[k] = Int32Array.from(sec.f[k]);
    const zero = new Float64Array(n);
    for (const m of BASE) ds.f[m] = sec.f[m] ? Float64Array.from(sec.f[m]) : zero;
    return ds;
  }

  // 이름 검색 — '단호박, 앵커, -0107' = (단호박|앵커) 포함 · 0107 포함은 제외 (dashboard.py _apply_name_search 와 같다)
  function nameMatcher(q) {
    const toks = String(q || '').split(',').map(t => t.trim()).filter(Boolean);
    const inc = toks.filter(t => !t.startsWith('-')).map(t => t.toLowerCase());
    const exc = toks.filter(t => t.startsWith('-')).map(t => t.slice(1).trim().toLowerCase()).filter(Boolean);
    if (!inc.length && !exc.length) return null;
    return v => { const s = String(v).toLowerCase(); return (!inc.length || inc.some(t => s.includes(t))) && !exc.some(t => s.includes(t)); };
  }

  // 조건 → 행 마스크 함수. where = {구분키: 값 배열|Set} · names = {구분키: 검색어} · bucket = 비용출처 묶음 이름
  function rowTest(ds, { where = null, names = null, bucket = null } = {}) {
    const conds = [];
    const add = (k, okVals) => { const set = okVals instanceof Set ? okVals : new Set(okVals); conds.push([ds.f[k], Uint8Array.from(ds.dims[k].map(v => set.has(v) ? 1 : 0))]); };
    if (where) for (const [k, v] of Object.entries(where)) if (v && ds.dims[k]) add(k, v);
    if (names) for (const [k, q] of Object.entries(names)) { const fn = nameMatcher(q); if (fn && ds.dims[k]) add(k, ds.dims[k].filter(fn)); }
    if (bucket && COST_BUCKETS[bucket] && ds.dims.src) add('src', bucketValues(ds.dims.src, bucket));
    if (!conds.length) return null;
    return i => { for (const [col, mask] of conds) if (!mask[col[i]]) return false; return true; };
  }

  // 일자별 합계 시리즈. group(i) 로 나누면 Map(그룹 → 시리즈), 아니면 시리즈 하나
  // 시리즈 = {지표: Float64Array(날짜수)} + has(그날 조건에 맞는 행이 있었는지)
  function emptySeries(nd) { const o = {}; for (const m of BASE) o[m] = new Float64Array(nd); o.has = new Uint8Array(nd); return o; }
  function daily(ds, filt = {}, group = null) {
    const nd = ds.dates.length, test = rowTest(ds, filt), out = new Map();
    const F = BASE.map(m => ds.f[m]);
    for (let i = 0; i < ds.n; i++) {
      if (test && !test(i)) continue;
      const key = group ? group(i) : '_';
      if (key == null) continue;
      let o = out.get(key);
      if (!o) { o = emptySeries(nd); out.set(key, o); }
      const d = ds.f.d[i];
      o.has[d] = 1;
      for (let j = 0; j < BASE.length; j++) o[BASE[j]][d] += F[j][i];
    }
    if (group) return out;
    return out.get('_') || emptySeries(nd);
  }

  // ── 기간 ───────────────────────────────────────────────────────────
  // 주 = ISO 주(월~일). 표시 'YY년 M월 N주차'는 그 주 목요일 기준 (dashboard.py week_of_month_label 과 같다)
  function weekInfo(n) {
    const mon = n - ((dow(n) + 6) % 7), t = iso(mon + 3);
    return { mon, key: iso(mon), y: +t.slice(0, 4), m: +t.slice(5, 7), w: Math.floor((+t.slice(8, 10) - 1) / 7) + 1 };
  }
  function periods(ds, grain) {
    const map = new Map(), list = [];
    for (let i = 0; i < ds.dates.length; i++) {
      const n = ds.dn[i], d = ds.dates[i];
      let key, label, short, y, m, start, end;
      if (grain === 'month') {
        y = +d.slice(0, 4); m = +d.slice(5, 7); key = d.slice(0, 7);
        label = `${String(y).slice(2)}년 ${m}월`; short = `${String(y).slice(2)}.${String(m).padStart(2, '0')}`;
        start = dnum(`${key}-01`); end = start + monthDays(y, m) - 1;
      } else if (grain === 'week') {
        const w = weekInfo(n); y = w.y; m = w.m; key = w.key;
        label = `${String(y).slice(2)}년 ${m}월 ${w.w}주차`; short = `${m}월${w.w}주`;
        start = w.mon; end = w.mon + 6;
      } else {
        y = +d.slice(0, 4); m = +d.slice(5, 7); key = d;
        label = `${String(y).slice(2)}년 ${m}월 ${+d.slice(8, 10)}일(${WD[dow(n)]})`; short = `${m}/${+d.slice(8, 10)}`;
        start = end = n;
      }
      let p = map.get(key);
      if (!p) { p = { key, label, short, y, m, start, end, idx: [] }; map.set(key, p); list.push(p); }
      p.idx.push(i);
    }
    list.sort((a, b) => a.start - b.start);
    for (const p of list) {
      p.lastN = ds.dn[p.idx[p.idx.length - 1]];
      p.partial = p.lastN < p.end;
      p.range = `${iso(p.start)} ~ ${iso(Math.min(p.end, p.lastN))}`;
    }
    return list;
  }
  // 현재 기간에서 실제로 쓰는 날짜 = 기간 날짜 중 조건에 맞는 데이터가 있는 날
  function curIdx(p, series) { return series ? p.idx.filter(i => series.has[i]) : p.idx.slice(); }
  // 비교 기간 날짜 인덱스
  //  - yoy / yoy2: 현재 날짜 각각의 364 / 728일 전 (동요일)
  //  - pop(직전 기간): 월 = 전월(진행 중이면 같은 일자까지), 주 = 7일 전, 일 = 1일 전
  function compareIdx(ds, p, grain, cmp, cur) {
    const out = [], take = n => { const i = ds.byNum.get(n); if (i != null) out.push(i); };
    if (cmp === 'pop' && grain === 'month') {
      let y = p.y, m = p.m - 1; if (!m) { m = 12; y -= 1; }
      const md = monthDays(y, m), lim = p.partial ? Math.min(md, p.lastN - p.start + 1) : md;
      const s = dnum(`${y}-${String(m).padStart(2, '0')}-01`);
      for (let k = 0; k < lim; k++) take(s + k);
      return out;
    }
    const shift = SHIFT[cmp] || (grain === 'week' ? 7 : 1);
    for (const i of cur) take(ds.dn[i] - shift);
    return out;
  }
  function cmpLabel(cmp, grain) { return cmp === 'yoy' ? '전년비' : cmp === 'yoy2' ? '전전년비' : ({ month: '전월비', week: '전주비', day: '전일비' })[grain]; }
  function cmpName(cmp, grain) { return cmp === 'yoy' ? '전년' : cmp === 'yoy2' ? '전전년' : ({ month: '전월', week: '전주', day: '전일' })[grain]; }

  // ── 합계 · 값 ──────────────────────────────────────────────────────
  function sumIdx(series, idx) {
    const s = { days: 0 };
    for (const m of BASE) { let v = 0; const a = series[m]; for (const i of idx) v += a[i]; s[m] = v; }
    for (const i of idx) if (series.has[i]) s.days++;
    return s;
  }
  // mode: 'sum' 누계 · 'avg' 일평균(합계형 지표만 ÷ 집행일수). 데이터가 없으면 null
  function value(metric, sums, mode) {
    if (!sums || !sums.days) return null;
    const v = metric.f(sums);
    if (v == null || !isFinite(v)) return null;
    if (mode === 'avg' && (metric.kind === 'money' || metric.kind === 'count')) return v / sums.days;
    return v;
  }

  // ── 백업 합치기 ────────────────────────────────────────────────────
  // 브라우저에 저장된 백업(base)에 새 백업(add)을 합친다
  //  - add 가 24년 파일(lock 있음): base 의 고정 구간(~lock) 전체와 add 의 날짜를 add 로 교체
  //  - base 에 고정 구간이 있으면: add 의 그 구간 날짜는 버린다(24년 파일 값 유지)
  //  - 그 외: add 에 있는 날짜는 교체, 나머지는 base 유지
  function mergeBackup(base, add) {
    if (!base || !base.row) return add;
    if (!add || !add.row) return base;
    const B = base.row, A = add.row, sb = base.source || {}, sa = add.source || {};
    const lock = sa.lock || sb.lock || null;
    const addLock = !!sa.lock;
    const keepA = A.dates.map(d => addLock || !lock || d > lock);
    const addDates = new Set(A.dates.filter((d, i) => keepA[i]));
    const keepB = B.dates.map(d => !addDates.has(d) && !(addLock && d <= lock));
    const dates = [...new Set([...B.dates.filter((d, i) => keepB[i]), ...addDates])].sort();
    const dIx = new Map(dates.map((d, i) => [d, i]));
    const dimKeys = [...new Set([...Object.keys(B.dims), ...Object.keys(A.dims)])];
    const mets = BASE.filter(m => B.f[m] || A.f[m]);
    const dims = {}, remap = { B: {}, A: {} };
    for (const k of dimKeys) {
      const bv = B.dims[k] || [''], av = A.dims[k] || [''];
      const vals = [...new Set([...bv, ...av])], ix = new Map(vals.map((v, i) => [v, i]));
      dims[k] = vals; remap.B[k] = bv.map(v => ix.get(v)); remap.A[k] = av.map(v => ix.get(v));
    }
    const f = { d: [] };
    for (const k of [...dimKeys, ...mets]) f[k] = [];
    const push = (S, side, keep) => {
      const n = S.f.d.length;
      for (let i = 0; i < n; i++) {
        const di = S.f.d[i];
        if (!keep[di]) continue;
        f.d.push(dIx.get(S.dates[di]));
        for (const k of dimKeys) f[k].push(S.f[k] ? remap[side][k][S.f[k][i]] : remap[side][k][0]);
        for (const m of mets) f[m].push(S.f[m] ? S.f[m][i] : 0);
      }
    };
    push(B, 'B', keepB);
    push(A, 'A', keepA);
    const files = [...(sb.files || []), ...(sa.files || [])];
    const source = {
      files, files24: (sa.files24 && sa.files24.length ? sa.files24 : sb.files24) || [], lock,
      missing: [...new Set([...(sb.missing || []), ...(sa.missing || [])])].sort(),
      from: dates[0], to: dates[dates.length - 1], days: dates.length, rows: f.d.length,
    };
    const replaced = B.dates.filter(d => addDates.has(d) || (addLock && d <= lock)).length;
    return {
      format: add.format, version: add.version, created: add.created, lastDate: source.to, source,
      row: { dates, dims, f, n: f.d.length, zero: BASE.filter(m => !mets.includes(m)) },
      merged: { added: addDates.size - B.dates.filter(d => addDates.has(d)).length, replaced, kept: keepB.filter(Boolean).length, ignored: keepA.filter(x => !x).length },
    };
  }

  // ── 표기 ───────────────────────────────────────────────────────────
  function fmtNum(v, dp = 0) {
    if (v == null || !isFinite(v)) return '–';
    if (Math.abs(v) < 0.5 * Math.pow(10, -dp)) v = 0;
    return v.toLocaleString('ko-KR', { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }
  // 광고비·거래액 = 백만원 소수 1자리 · CPA·CPC 등 = 원 · ROAS = % 정수 · 비율 = % (지표별 자릿수) · 수 = 정수(일평균은 소수 1자리)
  function fmt(m, v, mode) {
    if (v == null || !isFinite(v)) return '–';
    if (m.kind === 'money') return fmtNum(v / 1e6, 1);
    if (m.kind === 'won') return fmtNum(v, 0);
    if (m.kind === 'roas') return fmtNum(v * 100, 0) + '%';
    if (m.kind === 'ratio') return fmtNum(v * 100, m.dp != null ? m.dp : 2) + '%';
    return fmtNum(v, mode === 'avg' && Math.abs(v) < 1000 ? 1 : 0);
  }
  function unit(m, mode) {
    const per = mode === 'avg' ? '/일' : '';
    if (m.kind === 'money') return '백만원' + per;
    if (m.kind === 'won') return '원';
    if (m.kind === 'roas' || m.kind === 'ratio') return '%';
    return (m.k === 'imp' || m.k === 'clk' || m.k === 'uv' ? '' : '명') + per;
  }
  // 차트 축 값
  function scaled(m, v) {
    if (v == null || !isFinite(v)) return null;
    if (m.kind === 'money') return v / 1e6;
    if (m.kind === 'roas' || m.kind === 'ratio') return v * 100;
    return v;
  }
  // 증감 '+12.3%' · '△4.5%' (dashboard.py signed_pct 와 같은 기호)
  function signed(p, dp = 1) { if (p == null || !isFinite(p)) return '–'; return (p >= 0 ? '+' : '△') + Math.abs(p).toFixed(dp) + '%'; }
  // 드래그 합계에서 더할 수 있는 지표인지 (같은 단위 · 합산 의미가 있는 것)
  function additive(m) { return m.kind === 'money' || m.kind === 'count'; }

  const api = {
    BASE, METRIC_LIST, METRIC, SUMMARY, DETAIL, COST_BUCKETS, EVENTS, WD,
    normCost, bucketValues, div, pct, dnum, iso, dow, monthDays, weekInfo,
    prepare, nameMatcher, rowTest, daily, emptySeries, periods, curIdx, compareIdx, cmpLabel, cmpName, sumIdx, value,
    mergeBackup, fmtNum, fmt, unit, scaled, signed, additive,
  };
  root.DaCalc = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
