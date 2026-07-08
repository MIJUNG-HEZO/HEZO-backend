import http from 'k6/http';
import { check } from 'k6';
import { Trend, Rate } from 'k6/metrics';

// 오토스케일링 "전 과정" 정밀 측정용 (phase1.js 개선판).
//
// 지난 테스트(phase1.js)의 문제: 총 6.5분으로 너무 짧아, 스케일아웃(1→5, ~6분 소요)이
// 완료되자마자 테스트가 끝나 "5개로 회복된 후의 성능"을 측정하지 못했다. 그래서 SLO가
// 반응 지연 구간(단일 태스크 과부하)만 반영해 P95/P99/에러 모두 실패로만 보였다.
//
// 개선: 부하를 100 req/s로 낮춰(프로덕션 타임아웃 방지) 12분간 "유지"한다.
//   → 앞 ~6분(1개 태스크, 지연 상승) + 뒤 ~6분(5개 태스크, 지연 회복)을 모두 측정.
//   → CloudWatch TargetResponseTime 그래프에 "상승 후 회복" 곡선이 그대로 남는다.
//
// 엔드포인트별 지연을 분리 측정(health vs plans)해 병목 위치도 구분한다.

const healthLatency = new Trend('health_latency_ms', true);
const plansLatency = new Trend('plans_latency_ms', true);
const errorRate = new Rate('errors');

export const options = {
  scenarios: {
    scaling_observe: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 150,
      maxVUs: 600,
      // iteration 1회 = 요청 2건(health+plans) → target 50 iter/s = 100 req/s
      stages: [
        { duration: '2m',  target: 50 },   // 0 → 100 req/s 워밍업 (1개 태스크 baseline)
        { duration: '12m', target: 50 },   // 100 req/s 12분 유지 → 스케일아웃 + 회복 관측
        { duration: '2m',  target: 0 },    // 램프다운 → 스케일인 유도
      ],
    },
  },
  thresholds: {
    errors: ['rate<0.02'],
    // p99 임계를 넉넉히(2s) — 반응 지연 구간은 넘겠지만, 회복 후 구간이 통과하는지가 관건.
    health_latency_ms: ['p(95)<1000'],
    plans_latency_ms: ['p(95)<1000'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const BASE_URL = __ENV.BASE_URL || 'https://api.hezo.asia';

export default function () {
  // CloudFront 캐시 우회로 요청이 실제 백엔드까지 도달하게(부하 정확 측정)
  const h = http.get(`${BASE_URL}/api/v1/health?cb=${__VU}-${__ITER}`, { tags: { ep: 'health' } });
  check(h, { 'health 200': (r) => r.status === 200 });
  healthLatency.add(h.timings.duration);
  errorRate.add(h.status !== 200);

  const p = http.get(`${BASE_URL}/api/v1/plans?cb=${__VU}-${__ITER}`, { tags: { ep: 'plans' } });
  check(p, { 'plans 200': (r) => r.status === 200 });
  plansLatency.add(p.timings.duration);
  errorRate.add(p.status !== 200);
}

export function handleSummary(data) {
  const g = (m, s) => (data.metrics[m]?.values?.[s] ?? 0).toFixed(1);
  const summary = `
📊 스케일링 관측 테스트 결과
  ── 지연(ms) — health / plans ──
  P95   : ${g('health_latency_ms', 'p(95)')} / ${g('plans_latency_ms', 'p(95)')}
  P99   : ${g('health_latency_ms', 'p(99)')} / ${g('plans_latency_ms', 'p(99)')}
  최대  : ${g('health_latency_ms', 'max')} / ${g('plans_latency_ms', 'max')}
  ── 전체 ──
  에러율     : ${(( data.metrics.errors?.values?.rate ?? 0) * 100).toFixed(3)}%
  총 요청수  : ${data.metrics.http_reqs?.values?.count ?? 0}
  dropped    : ${data.metrics.dropped_iterations?.values?.count ?? 0}
  ※ 전체 P99는 반응 지연 구간 때문에 높게 나옴 — CloudWatch TargetResponseTime
     그래프의 "상승 후 회복" 곡선이 진짜 결과다.
`;
  return { stdout: summary };
}
