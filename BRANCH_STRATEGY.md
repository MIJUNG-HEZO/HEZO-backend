# 브랜치 전략

이 저장소는 단순하고 빠른 협업을 위해 GitHub Flow를 기반으로 운영한다.
배포 안정성이 필요해지는 시점에는 `develop` 브랜치를 함께 사용하는 방식으로 확장할 수 있다.

## 기본 원칙

1. 모든 작업은 별도 브랜치에서 진행한다.
2. `main` 브랜치에는 직접 커밋하지 않는다.
3. `main` 브랜치는 항상 배포 가능한 상태를 유지한다.
4. 하나의 브랜치에는 하나의 작업 단위만 담는다.
5. 작업 브랜치는 Pull Request를 통해서만 `main` 또는 `develop`에 병합한다.
6. 브랜치 이름은 영어 소문자, 숫자, 하이픈을 사용한다.
7. 브랜치 이름에는 작업 목적이 드러나야 한다.
8. 작업이 끝난 브랜치는 병합 후 삭제한다.
9. 장기간 유지되는 작업 브랜치는 주기적으로 기준 브랜치의 변경 사항을 반영한다.
10. 충돌 해결은 작업자가 우선 처리하고, 영향 범위가 크면 팀원에게 공유한다.

## 브랜치 종류

| 브랜치 | 설명 | 병합 대상 |
| --- | --- | --- |
| `main` | 운영 배포 기준 브랜치 | 없음 |
| `develop` | 개발 통합 브랜치. 필요 시 사용 | `main` |
| `feature/*` | 새로운 기능 개발 | `develop` 또는 `main` |
| `fix/*` | 일반 버그 수정 | `develop` 또는 `main` |
| `hotfix/*` | 운영 긴급 수정 | `main` |
| `release/*` | 배포 준비 및 QA | `main` |
| `docs/*` | 문서 작업 | `develop` 또는 `main` |
| `chore/*` | 설정, 의존성, 기타 작업 | `develop` 또는 `main` |
| `refactor/*` | 기능 변경 없는 구조 개선 | `develop` 또는 `main` |

## 브랜치 네이밍 규칙

```text
<type>/<issue-number>-<description>
```

이슈 번호가 없는 경우:

```text
<type>/<description>
```

- `type`: 작업 종류를 나타낸다.
- `issue-number`: 연결된 이슈 번호를 적는다. 선택 사항이다.
- `description`: 작업 내용을 짧게 영어 kebab-case로 작성한다.

## 브랜치 네이밍 예시

```text
feature/12-social-login
```

```text
fix/24-user-lookup-condition
```

```text
docs/commit-convention
```

```text
chore/add-env-example
```

```text
refactor/order-service-layer
```

```text
hotfix/payment-approval-timeout
```

## 작업 흐름

1. 기준 브랜치로 이동한다.

```bash
git checkout main
```

2. 최신 변경 사항을 가져온다.

```bash
git pull origin main
```

3. 작업 브랜치를 생성한다.

```bash
git checkout -b feature/12-social-login
```

4. 작업을 진행하고 커밋한다.

```bash
git add <file>
git commit -m "feat(auth): 소셜 로그인 기능 추가"
```

5. 원격 저장소에 브랜치를 올린다.

```bash
git push origin feature/12-social-login
```

6. Pull Request를 생성한다.
7. 리뷰와 CI 확인 후 병합한다.
8. 병합된 작업 브랜치를 삭제한다.

## 병합 전략

기본 병합 방식은 Squash Merge를 권장한다.

- PR 단위로 변경 이력을 깔끔하게 관리할 수 있다.
- 작업 중 발생한 작은 수정 커밋을 하나로 정리할 수 있다.
- Squash Merge 커밋 메시지는 커밋 컨벤션을 따른다.

단, 커밋 단위의 이력이 중요한 작업은 팀 합의 후 Merge Commit을 사용할 수 있다.

## `main` 브랜치 규칙

1. `main`은 항상 실행 가능하고 배포 가능한 상태여야 한다.
2. `main`에는 직접 push하지 않는다.
3. PR 리뷰와 필수 검사를 통과한 변경만 병합한다.
4. 운영 배포와 연결된 경우, `main` 병합 후 태그 또는 릴리즈 노트를 작성한다.

## `develop` 브랜치 규칙

`develop`은 개발 통합 브랜치가 필요한 경우에만 사용한다.

1. 여러 기능을 모아 QA해야 하는 경우 사용한다.
2. 기능 브랜치는 `develop`에서 생성하고 `develop`으로 병합한다.
3. 배포 준비가 완료되면 `develop`에서 `release/*` 브랜치를 생성한다.
4. 배포가 완료되면 `release/*`를 `main`에 병합한다.
5. `main`에 반영된 변경 사항은 다시 `develop`에 반영한다.

작은 규모의 프로젝트이거나 배포 흐름이 단순한 경우에는 `develop` 없이 `main` 기반 GitHub Flow만 사용한다.

## 핫픽스 흐름

운영 장애 또는 긴급 수정이 필요한 경우 `hotfix/*` 브랜치를 사용한다.

1. `main`에서 `hotfix/*` 브랜치를 생성한다.

```bash
git checkout main
git pull origin main
git checkout -b hotfix/payment-approval-timeout
```

2. 최소 범위로 수정한다.
3. 테스트를 실행하고 영향 범위를 확인한다.
4. PR을 생성해 `main`으로 병합한다.
5. 병합 후 배포한다.
6. `develop`을 사용하는 경우 hotfix 변경 사항을 `develop`에도 반영한다.

## 주의 사항

1. 브랜치 하나에 여러 기능을 섞지 않는다.
2. 리팩터링과 기능 변경은 가능한 한 브랜치를 분리한다.
3. 민감 정보나 개인 환경 설정 파일은 브랜치에 포함하지 않는다.
4. 충돌 해결 커밋은 변경 의도를 확인할 수 있게 신중하게 작성한다.
5. 다른 사람의 작업 브랜치를 수정해야 할 경우 사전에 공유한다.
6. 오래된 브랜치는 병합 전에 최신 기준 브랜치와 차이를 확인한다.

## 다음에 정할 문서 후보

브랜치 전략과 함께 아래 문서를 추가하는 것을 권장한다.

- `PR_CONVENTION.md`: PR 제목, 본문 템플릿, 리뷰 규칙, 머지 조건
- `ENVIRONMENT.md`: 환경변수 관리 방식, `.env` 파일 규칙, 비밀값 관리
- `NAMING_CONVENTION.md`: 패키지, 클래스, 함수, 변수, DB 테이블 네이밍 규칙
- `CODE_STYLE.md`: 포맷터, 린터, import 정렬, 예외 처리 규칙
