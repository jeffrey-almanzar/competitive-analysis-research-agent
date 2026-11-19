import http from 'k6/http';
import { check } from 'k6';

export const options = {
  thresholds: {
    http_req_duration: ['p(95)<200', 'p(99)<300'],
    http_req_failed: ['rate<0.01'],
  },
  stages: [
    { duration: '1m', target: 100 },
    { duration: '5m', target: 100 },
  ],
};

export default function () {
  const res = http.post(
    'http://localhost:8000/research',
    JSON.stringify({ query: 'AI tools' }),
    { headers: { 'Content-Type': 'application/json' } },
  );
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
}