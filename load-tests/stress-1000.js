import http from 'k6/http';
import { check } from 'k6';
import { Trend, Rate } from 'k6/metrics';

// 고부하 스트레스 테스트 (1000 RPS, max 10 태스크).
// 목적: 태스크를 10개까지 늘렸을 때 (a) 감당하는지 (b) RDS 커넥션 벽(~112)에 막히는지 관측.
// ⚠️ 프로덕션 DB를 커넥션 한계 근처로 밀 수 있음 → 모니터링 측(Claude)이 커넥션 90 도달 시 중단.
//
// 전제: infra/ecs-autoscaling.sh 를 max-capacity 10 으로 재적용한 상태여야 함.

const healthLatency = new Trend('health_latency_ms', true);
const plansLatency = new Trend('plans_latency_ms', true);
const errorRate = new Rate('errors');

export const options = {
  scenarios: {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 500,
      maxVUs: 3000,
      // iteration당 요청 2건(health+plans) → target 500 iter/s = 1000 req/s
      stages: [
        { duration: '2m',  target: 250 },   // 0 → 500 req/s 워밍업
        { duration: '2m',  target: 500 },   // 500 → 1000 req/s
        { duration: '10m', target: 500 },   // 1000 req/s 10분 유지 → 스케일아웃(최대 10) + 한계 관측
        { duration: '2m',  target: 0 },      // 램프다운
      ],
    },
  },
  thresholds: {
    errors: ['rate<0.05'],
    health_latency_ms: ['p(95)<2000'],
    plans_latency_ms: ['p(95)<2000'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const BASE_URL = __ENV.BASE_URL || 'https://api.hezo.asia';

export default function () {
  const h = http.get(`${BASE_URL}/api/v1/health?cb=${__VU}-${__ITER}`, { tags: { ep: 'health' } });
  check(h, { 'health 200': (r) => r.status === 200 });
  healthLatency.add(h.timings.duration);
  errorRate.add(h.status !== 200);

  const p = http.get(`${BASE_URL}/api/v1/plans?cb=${__VU}-${__ITER}`, { tags: { ep: 'plans' } });
  check(p, { 'plans 200': (r) => r.status === 200 });
  plansLatency.add(p.timings.duration);
  errorRate.add(p.status !== 200);
}
