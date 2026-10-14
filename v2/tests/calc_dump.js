// 테스트용: 백업(.json.gz) → calc.js 로 기간별 값 계산 → JSON 출력
// node tests/calc_dump.js BACKUP GRAIN BUCKET [where-json]
const fs = require('fs'), zlib = require('zlib'), path = require('path');
const C = require(path.join(__dirname, '..', 'calc.js'));
const [file, grain, bucket, whereJson] = process.argv.slice(2);
const P = JSON.parse(zlib.gunzipSync(fs.readFileSync(file)).toString('utf8'));
const R = C.prepare(P.row);
const where = whereJson ? JSON.parse(whereJson) : null;
const S = C.daily(R, { bucket: bucket === '-' ? null : bucket, where });
const out = [];
for (const p of C.periods(R, grain)) {
  const cur = C.curIdx(p, S);
  if (!cur.length) continue;
  const row = { key: p.key, label: p.label, days: cur.length };
  const sc = C.sumIdx(S, cur), sy = C.sumIdx(S, C.compareIdx(R, p, grain, 'yoy', cur));
  for (const k of C.SUMMARY.concat(C.DETAIL)) {
    row[k] = C.value(C.METRIC[k], sc, 'sum');
    row[k + '_avg'] = C.value(C.METRIC[k], sc, 'avg');
    row[k + '_yoy'] = C.value(C.METRIC[k], sy, 'sum');
  }
  out.push(row);
}
process.stdout.write(JSON.stringify(out));
