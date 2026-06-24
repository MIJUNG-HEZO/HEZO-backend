# HEZO Backend API 기능 정의서

> 작성일: 2026-06-22  
> 대상: HEZO 개발팀 전체  
> Base URL (production): `https://api.hezo.asia/api/v1`  
> Base URL (local): `http://localhost:8000/api/v1`

---

## 목차

1. [인증 방식](#1-인증-방식)
2. [공통 에러 응답 형식](#2-공통-에러-응답-형식)
3. [MVP 1차 API (PR #2 ~ #68, 머지 완료)](#3-mvp-1차-api-pr-2--68-머지-완료)
4. [MVP 2차 API (PR #70 ~ #78, 신규·변경)](#4-mvp-2차-api-pr-70--78-신규변경)
5. [환경변수 요약](#5-환경변수-요약)

---

## 1. 인증 방식

| 항목 | 내용 |
|---|---|
| Access Token | `Authorization: Bearer <access_token>` 헤더 |
| Refresh Token | HttpOnly Cookie (`hezo_refresh_token`) |
| 토큰 발급 | 로그인·소셜 로그인·토큰 재발급 응답 |
| 이메일 인증 필수 엔드포인트 | 사이트 생성(`POST /sites`), 결제 요청(`POST /billing/checkout`) |

---

## 2. 공통 에러 응답 형식

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "사람이 읽을 수 있는 설명",
    "details": { ... }
  }
}
```

검증 실패(422)도 동일 형식으로 표준화되어 있음:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청 데이터 검증 실패",
    "details": {
      "errors": [{ "field": "email", "message": "field required" }]
    }
  }
}
```

---

## 3. MVP 1차 API (PR #2 ~ #68, 머지 완료)

> **범위:** 코어 인증·사이트 CRUD·플랜·구독·결제 요청·이메일 인증  
> **마지막 PR:** #68 `fix(core): 1차 MVP 코드리뷰 반영 보안·정합성 개선`

---

### 3.1 Health

#### `GET /health`
- **설명:** 서버 상태 확인 (인증 불필요)
- **응답 200:**
```json
{ "status": "ok", "service": "hezo-api" }
```

---

### 3.2 Auth

#### `POST /auth/signup`
- **설명:** 이메일 회원가입 (기본 Free 구독 자동 생성)
- **인증:** 불필요
- **요청:**
```json
{
  "email": "user@example.com",
  "password": "string(8~128자)",
  "name": "홍길동",
  "phone": "010-1234-5678"
}
```
- **응답 201:**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "name": "홍길동",
  "phone": "010-1234-5678",
  "email_verified_at": null,
  "created_at": "2026-06-22T00:00:00Z",
  "updated_at": "2026-06-22T00:00:00Z"
}
```
- **에러:** `409 EMAIL_ALREADY_EXISTS`

---

#### `POST /auth/login`
- **설명:** 이메일 로그인. 응답 쿠키에 Refresh Token 설정.
- **인증:** 불필요
- **요청:**
```json
{ "email": "user@example.com", "password": "string" }
```
- **응답 200:**
```json
{ "access_token": "...", "token_type": "bearer" }
```
- **쿠키:** `Set-Cookie: hezo_refresh_token=...; HttpOnly; SameSite=Lax`
- **에러:** `401 INVALID_CREDENTIALS`, `401 ACCOUNT_DELETED`

---

#### `POST /auth/oauth/kakao`
- **설명:** 카카오 소셜 로그인. 신규 가입이면 `signup_required=true` 반환.
- **인증:** 불필요
- **요청:**
```json
{ "code": "카카오 인가코드", "redirect_uri": "https://..." }
```
- **응답 200:**
```json
{
  "signup_required": false,
  "access_token": "...",
  "token_type": "bearer",
  "signup_token": null,
  "provider": "kakao",
  "suggested_email": null,
  "suggested_name": null
}
```
- **신규 가입인 경우:** `signup_required=true`, `signup_token` 발급, `access_token=null`

---

#### `POST /auth/oauth/naver`
- **설명:** 네이버 소셜 로그인. 카카오와 동일한 응답 구조.
- **인증:** 불필요
- **요청:**
```json
{ "code": "네이버 인가코드", "redirect_uri": "https://..." }
```

---

#### `POST /auth/oauth/complete-signup`
- **설명:** 소셜 회원가입 완료 (signup_required=true일 때 호출)
- **인증:** 불필요
- **요청:**
```json
{
  "signup_token": "...",
  "email": "user@example.com",
  "name": "홍길동"
}
```
- **응답 200:** LoginResponse 동일 (`access_token`, 쿠키 설정)

---

#### `POST /auth/refresh`
- **설명:** Access Token 재발급 (Refresh Token Rotation)
- **인증:** Cookie `hezo_refresh_token` 필요
- **요청:** 없음 (쿠키에서 자동 추출)
- **응답 200:** `{ "access_token": "...", "token_type": "bearer" }`
- **에러:** `401 INVALID_REFRESH_TOKEN`, `401 REFRESH_TOKEN_REUSE_DETECTED` (토큰 재사용 탐지 시 전체 세션 폐기)

---

#### `POST /auth/logout`
- **설명:** 로그아웃 (Refresh Token 폐기 + 쿠키 삭제)
- **인증:** Cookie `hezo_refresh_token` (없어도 204 반환)
- **응답 204:** 없음

---

#### `DELETE /auth/me`
- **설명:** 회원 탈퇴 (소프트 딜리트, 연쇄 데이터 익명화)
- **인증:** Bearer 토큰 필수
- **응답 204:** 없음

---

#### `POST /auth/email-verification/request`
- **설명:** 이메일 인증 메일 발송 (SMTP)
- **인증:** Bearer 토큰 필수
- **요청:** 없음
- **응답 200:**
```json
{
  "expires_at": "2026-06-22T01:00:00Z",
  "verification_url": null
}
```

---

#### `POST /auth/email-verification/confirm`
- **설명:** 이메일 인증 토큰 검증 및 확인 처리
- **인증:** 불필요
- **요청:**
```json
{ "token": "이메일_링크_토큰" }
```
- **응답 200:**
```json
{ "email_verified_at": "2026-06-22T00:05:00Z" }
```
- **에러:** `400 INVALID_VERIFICATION_TOKEN`, `400 VERIFICATION_TOKEN_EXPIRED`

---

### 3.3 Users

#### `GET /users/me`
- **설명:** 내 정보 조회
- **인증:** Bearer 토큰 필수
- **응답 200:**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "name": "홍길동",
  "phone": "010-1234-5678",
  "email_verified_at": "2026-06-22T00:00:00Z",
  "email_verified": true,
  "created_at": "2026-06-22T00:00:00Z",
  "updated_at": "2026-06-22T00:00:00Z"
}
```

---

#### `PATCH /users/me`
- **설명:** 내 정보 수정 (이름·전화번호)
- **인증:** Bearer 토큰 필수
- **요청:**
```json
{
  "name": "홍길동",
  "phone": "010-9999-8888"
}
```
- **응답 200:** UserResponse (위와 동일)

---

### 3.4 Plans

#### `GET /plans`
- **설명:** 활성 플랜 목록 조회 (인증 불필요, 랜딩 페이지 요금표용)
- **인증:** 불필요
- **응답 200:**
```json
{
  "items": [
    {
      "code": "FREE",
      "name": "무료",
      "price_monthly": 0,
      "currency": "KRW",
      "max_sites": 1,
      "can_publish": false
    },
    {
      "code": "PRO",
      "name": "Pro",
      "price_monthly": 29000,
      "currency": "KRW",
      "max_sites": 3,
      "can_publish": true
    },
    {
      "code": "MAX",
      "name": "Max",
      "price_monthly": 99000,
      "currency": "KRW",
      "max_sites": 10,
      "can_publish": true
    }
  ]
}
```

---

#### `GET /plans/me/usage`
- **설명:** 내 플랜 사용량 조회 (사이트 생성 가능 여부 확인)
- **인증:** Bearer 토큰 필수
- **응답 200:**
```json
{
  "plan": { "code": "PRO", "name": "Pro" },
  "usage": {
    "max_sites": 3,
    "used_sites": 1,
    "remaining_sites": 2,
    "can_create_site": true,
    "can_publish": true
  }
}
```

---

### 3.5 Subscriptions

#### `GET /subscriptions/me`
- **설명:** 내 현재 구독 상태 조회
- **인증:** Bearer 토큰 필수
- **응답 200:**
```json
{
  "subscription": {
    "id": "uuid",
    "status": "active",
    "started_at": "2026-06-22T00:00:00Z",
    "ended_at": null,
    "renewed_at": null,
    "plan": {
      "code": "PRO",
      "name": "Pro",
      "price_monthly": 29000,
      "currency": "KRW",
      "max_sites": 3,
      "can_publish": true
    }
  }
}
```

---

### 3.6 Sites

#### `POST /sites`
- **설명:** 사이트 생성 (이메일 인증 필수, 플랜 한도 검증)
- **인증:** Bearer 토큰 + 이메일 인증 완료
- **요청:**
```json
{
  "name": "내 치과 홈페이지",
  "site_type": "landing",
  "module_key": "medical"
}
```
  - `site_type`: `landing` | `blog` | `store`
  - `module_key`: `medical` | `personal_blog` | `restaurant`
  - 유효한 조합: medical↔landing, personal_blog↔blog, restaurant↔store

- **응답 201:**
```json
{
  "id": "uuid",
  "name": "내 치과 홈페이지",
  "site_type": "landing",
  "module_key": "medical",
  "status": "draft",
  "is_published": false,
  "published_at": null,
  "created_at": "2026-06-22T00:00:00Z",
  "updated_at": "2026-06-22T00:00:00Z"
}
```
- **에러:** `403 PLAN_SITE_LIMIT_EXCEEDED`, `422 VALIDATION_ERROR`

---

#### `GET /sites`
- **설명:** 내 사이트 목록 조회
- **인증:** Bearer 토큰 필수
- **응답 200:**
```json
{
  "items": [ /* SiteResponse 배열 */ ],
  "total": 2
}
```

---

#### `GET /sites/{site_id}`
- **설명:** 사이트 상세 조회
- **인증:** Bearer 토큰 필수
- **응답 200:** SiteResponse

---

#### `PATCH /sites/{site_id}`
- **설명:** 사이트 기본 정보 수정 (이름·타입·모듈)
- **인증:** Bearer 토큰 필수
- **요청:** SiteUpdateRequest (`name`, `site_type`, `module_key`)
- **응답 200:** SiteResponse

---

#### `DELETE /sites/{site_id}`
- **설명:** 사이트 비활성화 (소프트 딜리트)
- **인증:** Bearer 토큰 필수
- **응답 204:** 없음

---

#### `GET /sites/{site_id}/publish-availability`
- **설명:** 발행 가능 여부 사전 체크 (발행 버튼 활성화 조건 확인)
- **인증:** Bearer 토큰 필수
- **응답 200:**
```json
{
  "can_publish": true,
  "reason": null,
  "site_status": "draft",
  "is_published": false,
  "plan_code": "PRO",
  "plan_can_publish": true
}
```

---

### 3.7 Billing

#### `POST /billing/checkout`
- **설명:** Toss Payments PG 결제 요청 파라미터 생성 (프론트 결제창 진입 전 호출)
- **인증:** Bearer 토큰 + 이메일 인증 완료
- **요청:**
```json
{ "plan_code": "PRO" }
```
- **응답 201:**
```json
{
  "payment_request_id": "uuid",
  "provider": "toss_payments",
  "plan_code": "PRO",
  "amount": 29000,
  "currency": "KRW",
  "status": "pending",
  "payment_params": {
    "clientKey": "test_ck_...",
    "orderId": "uuid",
    "orderName": "HEZO Pro 플랜",
    "amount": 29000,
    "customerEmail": "user@example.com",
    "customerName": "홍길동",
    "successUrl": "https://www.hezo.asia/billing/success",
    "failUrl": "https://www.hezo.asia/billing/fail"
  }
}
```

---

### 3.8 Dev (개발 환경 전용)

#### `POST /dev/subscriptions/upgrade`
- **설명:** 구독 업그레이드 (실결제 없이 플랜 변경 — 개발·테스트용)
- **인증:** Bearer 토큰 + 이메일 인증 완료
- **요청:**
```json
{ "plan_code": "PRO" }
```
- **응답 200:** MySubscriptionResponse
- **⚠️ 주의:** MVP 기간 한정 전 환경 허용. 실결제 전환 전 재제한 예정.

---

## 4. MVP 2차 API (PR #70 ~ #78, 신규·변경)

> **범위:** 에이전트 파이프라인 통합, 어드민, 결제 승인, 비밀번호 변경  
> **상태:** 미머지 (PR OPEN) — 아래 순서로 머지 진행 예정  
> **머지 순서:** #70 → #72 → #74 → #76 → #78

---

### 4.1 Admin (PR #70 신규)

> **접근 권한:** `role=admin` 계정 전용 (DB에서 직접 `UPDATE users SET role='admin'`)  
> `403 FORBIDDEN_ADMIN` 반환 시 권한 없음

#### `GET /admin/pipeline`
- **설명:** 전체 사이트 파이프라인 상태 목록 (DynamoDB `hezo_pipeline_state` scan)
- **인증:** Bearer 토큰 + admin 권한
- **응답 200:**
```json
{
  "items": [
    {
      "site_id": "site_tax_13_001",
      "publish_status": "published",
      "attempt": 1,
      "updated_at": "2026-06-22T00:00:00Z",
      "error_message": null
    }
  ],
  "total": 1
}
```

`publish_status` 값: `draft` | `building` | `validating` | `provisioning` | `published` | `failed` | `rolled_back`

---

#### `GET /admin/pipeline/{site_id}`
- **설명:** 특정 사이트 파이프라인 상태 조회
- **인증:** Bearer 토큰 + admin 권한
- **응답 200:** AdminPipelineItem (위와 동일)
- **미존재 시:** `publish_status: "not_found"` (404 아닌 200)

---

#### `GET /admin/users`
- **설명:** 전체 사용자 목록 (탈퇴 제외)
- **인증:** Bearer 토큰 + admin 권한
- **응답 200:**
```json
{
  "items": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "name": "홍길동",
      "role": "user",
      "email_verified": true,
      "created_at": "2026-06-22T00:00:00Z"
    }
  ],
  "total": 10
}
```

---

#### `GET /admin/metrics`
- **설명:** CloudWatch 메트릭 (현재 placeholder — P5 모니터링 스펙 확정 후 구현)
- **인증:** Bearer 토큰 + admin 권한
- **응답 200:**
```json
{
  "message": "CloudWatch 메트릭은 P5 모니터링 스펙 확정 후 연동 예정",
  "available": false
}
```

---

### 4.2 Sites — 온보딩 (PR #72 신규)

> 온보딩 데이터는 현재 백엔드 인메모리 스토어에 저장 (서버 재시작 시 초기화).  
> 추후 `sites` 테이블에 `onboarding_data JSONB` 컬럼 추가 예정.

#### `PATCH /sites/{site_id}/onboarding/business`
- **설명:** 비즈니스 이름 저장
- **인증:** Bearer 토큰 필수
- **요청:** `{ "business_name": "서울 밝은 치과" }`
- **응답 204:** 없음

---

#### `PATCH /sites/{site_id}/onboarding/services`
- **설명:** 제공 서비스 목록 저장
- **인증:** Bearer 토큰 필수
- **요청:** `{ "services": ["임플란트", "미백", "교정"] }`
- **응답 204:** 없음

---

#### `PATCH /sites/{site_id}/onboarding/contact`
- **설명:** 연락처 정보 저장
- **인증:** Bearer 토큰 필수
- **요청:**
```json
{
  "phone": "02-1234-5678",
  "email": "clinic@example.com",
  "address": "서울시 강남구 ...",
  "hours": "평일 09:00-18:00"
}
```
- **응답 204:** 없음

---

#### `PATCH /sites/{site_id}/onboarding/structure`
- **설명:** 템플릿 구조 설정
- **인증:** Bearer 토큰 필수
- **요청:**
```json
{
  "structure": "landing",
  "template_id": "landing_dental"
}
```
- **응답 204:** 없음

---

#### `PATCH /sites/{site_id}/onboarding/additional`
- **설명:** 추가 정보 (stub — 현재 no-op)
- **인증:** Bearer 토큰 필수
- **응답 204:** 없음

---

#### `POST /sites/{site_id}/onboarding/complete`
- **설명:** 온보딩 완료 마킹 (stub — 현재 no-op)
- **인증:** Bearer 토큰 필수
- **응답 204:** 없음

---

### 4.3 Sites — Contract (PR #72 신규)

#### `GET /sites/{site_id}/contract`
- **설명:** Contract JSON 조회 (온보딩 입력값 기반으로 구성)
- **인증:** Bearer 토큰 필수
- **응답 200:** (Contract JSON schema_version 0.1.0)
```json
{
  "schema_version": "0.1.0",
  "ids": {
    "project_id": "project_...",
    "site_id": "uuid",
    "tenant_id": "tenant_hezo_app"
  },
  "template": {
    "category": "landing",
    "template_id": "landing_dental",
    "slug": "dental"
  },
  "slots": {
    "business_name": "서울 밝은 치과",
    "industry": "general",
    "core_services": ["임플란트", "미백", "교정"],
    "phone": "02-1234-5678",
    "...": "..."
  },
  "slot_status": { "...": { "status": "filled", "confidence": 1.0 } },
  "gates": {
    "completeness_score": 0.9,
    "preview_ready": true,
    "generation_ready": true,
    "missing_items": []
  }
}
```

---

#### `POST /sites/{site_id}/contract`
- **설명:** Contract 생성 트리거 (stub — 현재 no-op, 추후 생성 에이전트 연결 예정)
- **인증:** Bearer 토큰 필수
- **응답 204:** 없음

---

### 4.4 Sites — Preview (PR #72 신규, PR #76 버그 수정)

#### `POST /sites/{site_id}/preview`
- **설명:** P3 빌드 워커 preview 모드 트리거
  - `P3_BUILD_ENDPOINT` 설정 시: P3 워커 `/build` 엔드포인트 호출 (비동기)
  - 미설정 시: mock 202 반환
- **인증:** Bearer 토큰 필수
- **요청:** 없음
- **응답 202:**
```json
{
  "site_id": "uuid",
  "preview_mode": "triggered",
  "preview_url": "https://preview.hezo.doodo.cloud/uuid/",
  "message": "프리뷰 생성이 시작되었습니다."
}
```
- mock 모드: `preview_mode: "mock"`, `preview_url: null`
- **에러:** `503 SERVICE_UNAVAILABLE` (P3 연결 실패)

> **변경 이력:** PR #76에서 P3 호출 경로 `/invocations` → `/build` 수정

---

#### `POST /sites/{site_id}/preview/retry-image`
- **설명:** 이미지 재생성 (stub — 현재 no-op)
- **응답 204:** 없음

---

#### `POST /sites/{site_id}/preview/retry-content`
- **설명:** 콘텐츠 재생성 (stub — 현재 no-op)
- **응답 204:** 없음

---

### 4.5 Sites — Publish & Pipeline (PR #72 신규, PR #76 버그 수정)

#### `POST /sites/{site_id}/publish`
- **설명:** 홈페이지 발행 — Step Functions 파이프라인 시작
  - `STEP_FUNCTIONS_ARN` 설정 시: contract JSON → S3 업로드 → Step Functions 실행
  - 미설정 시: 로컬 즉시 완료 모드
- **인증:** Bearer 토큰 + 이메일 인증 완료
- **요청:** 없음
- **응답 200:**
```json
{
  "site_id": "uuid",
  "mode": "aws_pipeline",
  "pipeline_status": "running",
  "execution_arn": "arn:aws:states:ap-northeast-2:...",
  "message": "파이프라인이 시작되었습니다."
}
```
- 로컬 모드: `mode: "local"`, `pipeline_status: "published"`, `execution_arn: null`
- **에러:** `403 FORBIDDEN` (발행 불가 조건), `503` (S3/SFN 연결 실패)

---

#### `GET /sites/{site_id}/pipeline/status`
- **설명:** 파이프라인 실행 상태 폴링 (프론트에서 3초마다 호출)
  - DynamoDB `hezo_pipeline_state` 우선 조회 → fallback Step Functions
- **인증:** Bearer 토큰 필수
- **응답 200:**
```json
{
  "site_id": "uuid",
  "pipeline_status": "running",
  "render_spec_s3_key": "sites/uuid/render_spec.json",
  "execution_arn": "arn:aws:states:...",
  "updated_at": "2026-06-22T00:00:00Z",
  "error": null
}
```

`pipeline_status` 매핑 (DynamoDB `publish_status` → 프론트 표시값):

| DynamoDB `publish_status` | `pipeline_status` 반환값 |
|---|---|
| `building` / `validating` | `running` |
| `published` | `published` |
| `failed` / `rolled_back` | `generation_failed` |
| DynamoDB 없음 (로컬 모드) | `published` |

> **변경 이력:** PR #76에서 DynamoDB 조회 필드명 `pipeline_status` → `publish_status` 수정

---

### 4.6 Sites — Chat (PR #72 신규)

#### `POST /sites/{site_id}/chat`
- **설명:** P1 챗봇 에이전트 대화
  - `P1_AGENT_ENDPOINT` 설정 시: AgentCore `/invocations` 포워딩
  - 미설정 시: 순차 mock 응답 (5단계 시나리오)
- **인증:** Bearer 토큰 필수
- **요청:**
```json
{
  "session_id": "session-uuid",
  "user_message": "안녕하세요, 저는 치과 원장입니다.",
  "domain": "medical",
  "template_id": "landing_dental"
}
```
- **응답 200:**
```json
{
  "session_id": "session-uuid",
  "assistant_message": "안녕하세요! 비즈니스 이름을 알려주세요.",
  "turn_status": "answer_accepted",
  "next_stage": "proactive_questioning",
  "slot_filled": { "business_name": "서울 밝은 치과" },
  "missing_slots": ["phone", "core_services"],
  "mock": false
}
```

`turn_status` 값:
| 값 | 의미 |
|---|---|
| `answer_accepted` | 입력 정상 수신, 다음 질문 |
| `answer_rejected` | 입력 거절 (오프토픽 등), 재질문 |
| `ready_for_contract_compile` | 필수 슬롯 채움 완료, 프리뷰 준비 |

`next_stage` 값: `proactive_questioning` | `contract_compile` | `retry_answer`

---

### 4.7 Billing — 결제 승인 (PR #74 / #78 신규)

#### `POST /billing/confirm`
- **설명:** Toss Payments 결제 완료 승인 (successUrl redirect 후 프론트에서 호출)
  1. `orderId`로 payment_request 조회 (락)
  2. 금액 검증
  3. 중복 호출 방지 (이미 APPROVED면 현재 상태 그대로 반환)
  4. Toss `/v1/payments/confirm` API 호출
  5. subscription 플랜 업그레이드
  6. billing_event 기록
- **인증:** Bearer 토큰 필수
- **요청:**
```json
{
  "paymentKey": "toss_payment_key",
  "orderId": "uuid",
  "amount": 29000
}
```
- **응답 200:**
```json
{
  "payment_request_id": "uuid",
  "plan_code": "PRO",
  "amount": 29000,
  "status": "approved"
}
```
- **에러:** `404 PAYMENT_REQUEST_NOT_FOUND`, `400 PAYMENT_AMOUNT_MISMATCH`, `502 TOSS_API_ERROR`

---

### 4.8 Auth — 비밀번호 변경 (PR #74 신규)

#### `PATCH /auth/me/password`
- **설명:** 설정 페이지 비밀번호 변경 (이메일 가입 계정만 가능)
- **인증:** Bearer 토큰 필수
- **요청:**
```json
{
  "current_password": "현재비밀번호",
  "new_password": "새비밀번호(8자이상)"
}
```
- **응답 204:** 없음
- **에러:** `400 INVALID_CURRENT_PASSWORD`, `400 SOCIAL_ACCOUNT_NO_PASSWORD` (소셜 로그인 계정)

---

## 5. 환경변수 요약

| 변수 | 필수 | 설명 | 기본값 |
|---|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL 연결 URL | - |
| `JWT_SECRET_KEY` | ✅ | JWT 서명키 (32자 이상 강제) | - |
| `COOKIE_SECURE` | ✅ prod | Refresh Cookie Secure 플래그 | `false` |
| `APP_ENV` | - | `production` 시 Swagger 비활성, dev endpoint 제한 | `development` |
| `CORS_ALLOWED_ORIGINS` | - | 허용 Origin 목록 (콤마 구분) | `http://localhost:3000` |
| `TOSS_PAYMENTS_SECRET_KEY` | ✅ (결제) | Toss 시크릿 키 (`sk_...`) | - |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | ✅ (이메일) | SMTP 인증 메일 발송 | - |
| `KAKAO_CLIENT_ID` | ✅ (카카오) | 카카오 OAuth 앱 ID | - |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | ✅ (네이버) | 네이버 OAuth | - |
| `P1_AGENT_ENDPOINT` | - (MVP2) | P1 AgentCore URL (미설정 시 mock) | - |
| `P3_BUILD_ENDPOINT` | - (MVP2) | P3 빌드 워커 ALB URL | - |
| `STEP_FUNCTIONS_ARN` | - (MVP2) | Step Functions 상태머신 ARN | - |
| `ARTIFACTS_BUCKET` | - (MVP2) | S3 artifacts 버킷명 | `hezo-artifacts` |
| `AWS_REGION` | - (MVP2) | AWS 리전 | `ap-northeast-2` |

---

## 부록 — MVP 1차 PR 이력

| PR | 제목 | 머지일 |
|---|---|---|
| #2 | FastAPI 프로젝트 공통 기반 세팅 | 2026-06-06 |
| #4 | PostgreSQL DB 연결 및 세션 구조 세팅 | 2026-06-07 |
| #6 | 사이트 슬롯 생성 API | 2026-06-07 |
| #9 | Alembic 마이그레이션 기반 세팅 | 2026-06-07 |
| #10 | 사이트 목록 조회 API | 2026-06-07 |
| #13 | 사이트 상세 조회 API | 2026-06-07 |
| #15 | 사이트 기본 정보 수정 API | 2026-06-07 |
| #16 | 이메일 회원가입 | 2026-06-07 |
| #19 | 플랜 목록 조회 API | 2026-06-07 |
| #20 | 이메일 로그인 및 토큰 발급 | 2026-06-07 |
| #22 | current_user 인증 dependency | 2026-06-07 |
| #25 | 내 구독 상태 조회 API | 2026-06-08 |
| #26 | 이메일 인증 메일 요청 | 2026-06-08 |
| #29 | 내 플랜 사용량 조회 API | 2026-06-08 |
| #30 | 이메일 인증 처리 | 2026-06-08 |
| #32 | 사이트 삭제/비활성화 API | 2026-06-08 |
| #35 | 플랜별 사이트 생성 제한 검증 보강 | 2026-06-08 |
| #37 | 발행 가능 여부 체크 API | 2026-06-08 |
| #40 | 회원가입 시 기본 Free 구독 생성 | 2026-06-08 |
| #41 | SMTP 이메일 인증 메일 발송 연동 | 2026-06-08 |
| #43 | 결제 요청 이력 저장 기반 | 2026-06-08 |
| #46 | 결제 이벤트 로그 저장 기반 | 2026-06-08 |
| #50 | Refresh Token rotation 재발급 | 2026-06-08 |
| #51 | 카카오 소셜 로그인 | 2026-06-08 |
| #53 | PG 요청 파라미터 생성 | 2026-06-08 |
| #54 | 로그아웃 | 2026-06-08 |
| #57 | 결제 요청 생성 API | 2026-06-08 |
| #59 | 네이버 소셜 로그인 | 2026-06-08 |
| #60 | 구독 플랜 업그레이드 로직 | 2026-06-09 |
| #63 | 내 정보 조회 및 수정 | 2026-06-09 |
| #64 | 회원 탈퇴 | 2026-06-09 |
| #66 | 플랜 업그레이드 테스트 API | 2026-06-09 |
| #68 | 1차 MVP 코드리뷰 반영 보안·정합성 개선 | 2026-06-09 |

## 부록 — MVP 2차 PR 이력 (미머지)

| PR | 제목 | 상태 |
|---|---|---|
| #70 | 어드민 대시보드 백엔드 (User.role, require_admin, /admin/* API) | OPEN |
| #72 | P1 chat + preview P3 프록시 엔드포인트 (에이전트 통합 준비) | OPEN |
| #74 | POST /billing/confirm + PATCH /auth/me/password | OPEN |
| #76 | fix: P3 preview /build 경로 오류 + DynamoDB publish_status 필드명 수정 | OPEN |
| #78 | feat(billing): POST /billing/confirm + CASCADE DELETE + dev endpoint 전 환경 허용 | OPEN |
