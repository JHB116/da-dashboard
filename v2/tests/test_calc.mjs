// node --test tests/test_calc.mjs — calc.js 단위 테스트 (가짜 데이터)
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const C = createRequire(import.meta.url)('../calc.js');

// 2026-08-01 ~ 2026-10-11 매일 광고비 = 날짜 일(day)값 × 1,000원, 2025-08 ~ 2025-10 같은 형식
function make(from, to, extra = {}) {
  const dates = [];
  for (let n = C.dnum(from); n <= C.dnum(to); n++) dates.push(C.iso(n));
  const f = { d: dates.map((_, i) => i), md: dates.map(() => 0), src: dates.map(() => 0), cost: dates.map(d => +d.slice(8) * 1000), join: dates.map(() => 2) };
  return { dates, dims: { md: ['카카오'], src: ['거래액확대'] }, f, n: dates.length, ...extra };
}
const sec = (() => { const a = make('2025-08-01', '2025-10-31'), b = make('2026-08-01', '2026-10-11');
  return { dates: [...a.dates, ...b.dates], dims: a.dims, n: a.n + b.n,
    f: Object.fromEntries(Object.keys(a.f).map(k => [k, k === 'd' ? [...a.f.d, ...b.f.d.map(i => i + a.n)] : [...a.f[k], ...b.f[k]]])) }; })();
const R = C.prepare(sec), S = C.daily(R, { bucket: 'TOTAL' });

test('월 · 전월비는 진행 중인 달이면 같은 일자까지', () => {
  const ps = C.periods(R, 'month'), oct = ps.find(p => p.key === '2026-10');
  assert.equal(oct.partial, true);
  const cur = C.curIdx(oct, S), prev = C.compareIdx(R, oct, 'month', 'pop', cur);
  assert.deepEqual(prev.map(i => R.dates[i]), Array.from({ length: 11 }, (_, k) => `2026-09-${String(k + 1).padStart(2, '0')}`));
});
test('전년비는 364일 전 같은 요일', () => {
  const p = C.periods(R, 'day').find(p => p.key === '2026-10-11');
  const idx = C.compareIdx(R, p, 'day', 'yoy', C.curIdx(p, S));
  assert.equal(R.dates[idx[0]], '2025-10-12');
  assert.equal(C.dow(C.dnum('2025-10-12')), C.dow(C.dnum('2026-10-11')));
});
test('주 · 전주 = 7일 전, 주차 라벨은 목요일 기준', () => {
  const p = C.periods(R, 'week').find(p => p.key === '2026-09-28');   // 9/28(월)~10/4, 목요일 10/1
  assert.equal(p.label, '26년 10월 1주차');
  const idx = C.compareIdx(R, p, 'week', 'pop', C.curIdx(p, S));
  assert.equal(R.dates[idx[0]], '2026-09-21');
});
test('일평균 = 합계 ÷ 집행일수, 비율은 합계 ÷ 합계', () => {
  const p = C.periods(R, 'month').find(p => p.key === '2026-09');
  const s = C.sumIdx(S, C.curIdx(p, S));
  assert.equal(s.days, 30);
  assert.equal(C.value(C.METRIC.cost, s, 'avg'), 465 * 1000 / 30);
  assert.equal(C.value(C.METRIC.jcpa, s, 'avg'), 465 * 1000 / 60);
});
test('비용출처 묶음은 공백 · 대소문자 · 전각 슬래시를 무시', () => {
  assert.deepEqual(C.bucketValues(['서비스비용-e영업', 'E영업／정산제외', '기타'], 'TOTAL'), ['서비스비용-e영업', 'E영업／정산제외']);
  const none = C.daily(R, { bucket: '신규고객확대' });
  assert.equal(none.has.reduce((a, b) => a + b, 0), 0);
});
test('이름 검색: 포함 · 제외', () => {
  const m = C.nameMatcher('단호박, 앵커, -0107');
  assert.equal(m('단호박_0101'), true); assert.equal(m('앵커_0107'), false); assert.equal(m('기타'), false);
});
test('병합: 24년 고정 구간은 매일 파일로 바뀌지 않는다', () => {
  const y24 = { format: 'da-dashboard-backup', source: { lock: '2024-12-31', files24: ['24.csv'] }, row: make('2024-12-25', '2024-12-31') };
  const daily = { format: 'da-dashboard-backup', source: { files: ['d.csv'] }, row: make('2024-12-30', '2025-01-03') };
  daily.row.f.cost = daily.row.f.cost.map(v => v * 10);
  const m1 = C.mergeBackup(y24, daily);
  const R1 = C.prepare(m1.row), s1 = C.daily(R1);
  const at = d => s1.cost[R1.byNum.get(C.dnum(d))];
  assert.equal(at('2024-12-30'), 30000);          // 24년 값 유지
  assert.equal(at('2025-01-02'), 20000);          // 매일 파일 값
  assert.equal(m1.source.lock, '2024-12-31');
  assert.equal(m1.merged.ignored, 2);
  // 순서 반대(매일 먼저 → 24년 나중)도 같은 결과
  const m2 = C.mergeBackup(daily, y24), R2 = C.prepare(m2.row), s2 = C.daily(R2);
  assert.deepEqual([...s2.cost], [...s1.cost]);
  assert.deepEqual(m2.row.dates, m1.row.dates);
});
test('드릴다운 트리: 단계 합 = 전체 합', () => {
  const t = C.tree(R, { bucket: 'TOTAL' }, ['md', 'src'], [R.dates.map((_, i) => i), []]);
  const kids = C.children(t, '', 0);
  assert.equal(kids.reduce((a, n) => a + n.s[0].cost, 0), t.total[0].cost);
  const sub = C.children(t, kids[0].key, 1);
  assert.equal(sub.reduce((a, n) => a + n.s[0].cost, 0), kids[0].s[0].cost);
  assert.deepEqual(C.keyWhere(R, ['md', 'src'], sub[0].key), { md: ['카카오'], src: ['거래액확대'] });
});
test('목표: 진행 중인 주 = 주 목표 × 경과일/7 · 묶음 밖은 없음', () => {
  const T = { weekly: { '2026-10-05': { spend: 700, rev: 1400 } }, monthly: {} };
  const p = { key: '2026-10-05', start: C.dnum('2026-10-05'), end: C.dnum('2026-10-11') };
  assert.deepEqual(C.periodTarget(T, 'TOTAL', 'week', p, '2026-10-07'), { spend: 300, rev: 600, roas: 2 });
  assert.equal(C.periodTarget(T, '신규고객확대', 'week', p, '2026-10-07'), null);
});
test('병합: 목표 · 메모 유지', () => {
  const a = { format: 'da-dashboard-backup', source: {}, row: make('2026-10-01', '2026-10-02'), memos: { k: { text: 'a', ts: 1 } } };
  const t = { format: 'da-dashboard-backup', source: {}, targets: { monthly: {} } };
  const m = C.mergeBackup(a, t);
  assert.ok(m.row && m.targets && m.memos.k.text === 'a');
  const m2 = C.mergeBackup(m, { format: 'da-dashboard-backup', source: {}, row: make('2026-10-03', '2026-10-03'), memos: { k: { text: 'b', ts: 2 } } });
  assert.equal(m2.memos.k.text, 'b'); assert.ok(m2.targets);
});
test('병합: 목표만 먼저 넣고 데이터를 넣어도 목표 유지', () => {
  const t = { format: 'da-dashboard-backup', source: {}, targets: { monthly: { TOTAL: {} } } };
  const d = { format: 'da-dashboard-backup', source: {}, row: make('2026-10-01', '2026-10-02') };
  const m = C.mergeBackup(C.mergeBackup(null, t), d);
  assert.ok(m.row && m.targets && m.targets.monthly);
});

test('AF코드 섹션 합치기: 새 쪽 날짜 우선 · 최근 92일만', () => {
  const sec = (from, n, v) => { const dates = []; for (let i = 0; i < n; i++) dates.push(C.iso(C.dnum(from) + i)); return { dates, dims: { af: ['A'] }, f: { d: dates.map((_, i) => i), af: dates.map(() => 0), cost: dates.map(() => v) }, n }; };
  const m = C.mergeAf(sec('2026-06-01', 100, 1), sec('2026-09-01', 10, 2), '2026-09-10');
  assert.equal(m.dates.length, 92);
  assert.equal(m.dates[m.dates.length - 1], '2026-09-10');
  assert.equal(m.f.cost[m.f.d.indexOf(m.dates.indexOf('2026-09-05'))], 2);
  assert.equal(C.mergeAf(null, null, '2026-09-10'), null);
});
