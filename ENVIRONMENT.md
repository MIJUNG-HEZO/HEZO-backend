# 환경변수 관리 규칙

이 문서는 프로젝트의 환경변수와 비밀값을 안전하고 일관되게 관리하기 위한 규칙을 정의한다.
환경변수는 실행 환경마다 달라지는 설정값을 코드와 분리하기 위해 사용한다.

## 기본 원칙

1. 환경변수는 코드에 하드코딩하지 않는다.
2. 실제 비밀값은 Git에 커밋하지 않는다.
3. 공유 가능한 변수 목록과 예시는 `.env.example`에 작성한다.
4. 로컬에서 사용하는 실제 값은 `.env` 또는 개인 로컬 환경에만 둔다.
5. 운영 환경의 비밀값은 배포 플랫폼 또는 Secret Manager에서 관리한다.
6. 환경변수 이름은 대문자 스네이크 케이스를 사용한다.
7. 환경변수 추가, 수정, 삭제 시 PR 본문에 변경 내용을 공유한다.
8. 환경변수 기본값이 필요한 경우 코드에서 의도를 명확히 드러낸다.
9. 필수 환경변수가 누락되면 애플리케이션 시작 시점에 빠르게 실패하도록 한다.
10. 민감 정보는 로그, 에러 메시지, PR 본문, 문서에 노출하지 않는다.

## 파일 구성

| 파일 | 설명 | 커밋 여부 |
| --- | --- | --- |
| `.env` | 로컬 개발용 실제 환경변수 | 커밋 금지 |
| `.env.local` | 개인 로컬 오버라이드 값 | 커밋 금지 |
| `.env.example` | 팀에 공유할 환경변수 예시 | 커밋 허용 |
| `.env.test` | 테스트용 환경변수. 민감값이 없을 때만 사용 | 필요 시 허용 |
| `.env.production` | 운영 환경 실제 값 | 커밋 금지 |

## `.gitignore` 규칙

실제 환경변수 파일은 Git에 포함하지 않는다.
아래 항목이 `.gitignore`에 포함되어 있는지 확인한다.

```gitignore
.env
.env.*
!.env.example
!.env.test
```

`.env.test`에 실제 비밀값이 들어가는 경우에는 커밋하지 않는다.

## `.env.example` 작성 규칙

`.env.example`은 필요한 환경변수 목록을 팀원이 빠르게 파악하기 위한 문서 역할을 한다.
실제 비밀값 대신 예시값 또는 빈 값을 작성한다.

```env
APP_ENV=local
APP_PORT=8080
DATABASE_URL=postgresql://user:password@localhost:5432/hezo
JWT_SECRET_KEY=change-me
OAUTH_KAKAO_CLIENT_ID=your-client-id
OAUTH_KAKAO_CLIENT_SECRET=your-client-secret
```

작성 규칙:

1. 새 환경변수를 추가하면 `.env.example`도 함께 수정한다.
2. 예시값은 실제 서비스 값과 다르게 작성한다.
3. 어떤 값인지 이름만으로 알기 어려운 경우 주석을 추가한다.
4. 사용하지 않는 환경변수는 제거한다.
5. 선택값과 필수값은 문서나 주석으로 구분한다.

## 네이밍 규칙

환경변수 이름은 대문자 스네이크 케이스를 사용한다.

```text
<DOMAIN>_<NAME>
```

예시:

```env
APP_PORT=8080
DATABASE_URL=postgresql://user:password@localhost:5432/hezo
JWT_SECRET_KEY=change-me
KAKAO_CLIENT_ID=your-client-id
KAKAO_CLIENT_SECRET=your-client-secret
S3_BUCKET_NAME=hezo-dev
```

권장 prefix:

| Prefix | 용도 |
| --- | --- |
| `APP_` | 애플리케이션 실행 설정 |
| `DATABASE_` | 데이터베이스 연결 설정 |
| `REDIS_` | Redis 연결 설정 |
| `JWT_` | JWT 인증 관련 설정 |
| `OAUTH_` | OAuth 제공자 공통 설정 |
| `KAKAO_` | 카카오 API 설정 |
| `NAVER_` | 네이버 API 설정 |
| `AWS_` | AWS 인증 및 리소스 설정 |
| `S3_` | S3 스토리지 설정 |
| `MAIL_` | 메일 발송 설정 |

## 환경 구분

환경은 아래 기준으로 구분한다.

| 환경 | 설명 |
| --- | --- |
| `local` | 개인 로컬 개발 환경 |
| `test` | 자동 테스트 실행 환경 |
| `dev` | 팀 개발 서버 환경 |
| `staging` | 운영 배포 전 검증 환경 |
| `production` | 실제 운영 환경 |

환경 구분 변수는 아래 이름을 권장한다.

```env
APP_ENV=local
```

## 비밀값 관리

비밀값은 외부에 노출되면 안 되는 값을 의미한다.

예시:

- DB 비밀번호
- JWT Secret
- OAuth Client Secret
- AWS Access Key
- API Token
- 암호화 키
- 결제, 메시징, 메일 서비스 Secret

관리 규칙:

1. 비밀값은 Git에 커밋하지 않는다.
2. 비밀값은 메신저, PR, 이슈, 문서에 직접 공유하지 않는다.
3. 비밀값 공유가 필요하면 팀에서 정한 안전한 전달 방식을 사용한다.
4. 유출이 의심되면 즉시 폐기하고 재발급한다.
5. 운영 비밀값은 배포 플랫폼의 Secret 기능 또는 Secret Manager를 사용한다.

## 권장 관리 도구

프로젝트 초기에는 아래 방식으로 시작한다.

| 용도 | 권장 방식 |
| --- | --- |
| 로컬 개발 | `.env` + `.env.example` |
| 팀 공유용 변수 목록 | `.env.example` |
| 운영 비밀값 | 배포 플랫폼 Secret 또는 Secret Manager |
| 개인 로컬 자동 로딩 | `direnv` 선택 사용 |

`direnv`를 사용하는 경우 `.envrc`에는 실제 비밀값을 직접 작성하지 않는다.
필요하다면 `.env`를 로드하는 방식으로 사용한다.

```bash
dotenv
```

`.envrc`를 커밋할 경우 팀원에게 동일하게 필요한 설정만 포함한다.
개인 경로나 개인 비밀값이 들어가면 커밋하지 않는다.

## 환경변수 추가 절차

1. 환경변수가 꼭 필요한 값인지 확인한다.
2. 변수 이름을 네이밍 규칙에 맞게 정한다.
3. 코드에서 환경변수를 읽도록 구현한다.
4. 필수값인 경우 시작 시점 검증을 추가한다.
5. `.env.example`에 예시값을 추가한다.
6. PR 본문에 환경변수 변경 사항을 작성한다.
7. 배포 환경에 실제 값을 등록한다.
8. 필요한 경우 팀에 설정 방법을 공유한다.

## PR 작성 시 환경변수 변경 공유

환경변수 변경이 있는 PR은 아래 내용을 작성한다.

```markdown
## 환경변수 / 설정 변경
- [ ] 환경변수 또는 설정 변경 없음
- [x] 환경변수 또는 설정 변경 있음
  - 추가: KAKAO_CLIENT_ID, KAKAO_CLIENT_SECRET
  - 수정: 없음
  - 삭제: 없음
  - 배포 환경 등록 필요: 예
```

## 로컬 설정 예시

처음 프로젝트를 실행하는 팀원은 `.env.example`을 복사해 `.env`를 만든다.

```bash
cp .env.example .env
```

이후 `.env`의 값을 개인 로컬 환경에 맞게 수정한다.

```env
APP_ENV=local
APP_PORT=8080
DATABASE_URL=postgresql://user:password@localhost:5432/hezo
JWT_SECRET_KEY=local-development-secret
```

## 보안 사고 대응

비밀값이 Git, PR, 이슈, 로그 등에 노출된 경우 아래 순서로 대응한다.

1. 노출된 비밀값을 즉시 폐기한다.
2. 새 비밀값을 발급한다.
3. 로컬, 개발, 운영 환경에 새 값을 반영한다.
4. 노출 경로를 확인하고 제거한다.
5. 같은 문제가 반복되지 않도록 `.gitignore`, 로그, 문서, 리뷰 체크리스트를 점검한다.

이미 Git 이력에 포함된 비밀값은 파일 삭제만으로 완전히 제거되지 않는다.
필요한 경우 이력 정리와 키 재발급을 함께 진행한다.

## 주의 사항

1. 실제 운영 값은 `.env.example`에 작성하지 않는다.
2. 환경변수 값에 따옴표가 필요한지 사용하는 프레임워크 규칙을 확인한다.
3. URL, 포트, boolean 값은 코드에서 타입 변환을 명확히 처리한다.
4. 기본값이 운영에 위험한 경우 기본값을 두지 않는다.
5. 로그에 환경변수 전체를 출력하지 않는다.
6. 테스트용 비밀값이라도 외부 서비스와 연결된 실제 값이면 커밋하지 않는다.

## 다음에 정할 문서 후보

환경변수 관리 규칙과 함께 아래 문서를 추가하는 것을 권장한다.

- `NAMING_CONVENTION.md`: 패키지, 클래스, 함수, 변수, DB 테이블 네이밍 규칙
- `CODE_STYLE.md`: 포맷터, 린터, import 정렬, 예외 처리 규칙
