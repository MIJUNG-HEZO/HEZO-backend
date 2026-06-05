# 기여 가이드

이 문서는 HEZO-backend 저장소에서 협업할 때 따라야 할 기본 흐름을 안내한다.
자세한 규칙은 각 컨벤션 문서를 기준으로 한다.

## 작업 흐름

1. 최신 `main` 브랜치를 기준으로 작업 브랜치를 생성한다.
2. 하나의 브랜치에는 하나의 작업 단위만 담는다.
3. 커밋 메시지는 커밋 컨벤션을 따른다.
4. 작업이 완료되면 Pull Request를 생성한다.
5. PR 본문에 변경 목적, 구현 내용, 테스트 결과를 작성한다.
6. 리뷰와 필수 검사를 통과한 뒤 병합한다.
7. 병합된 작업 브랜치는 삭제한다.

## 브랜치

브랜치는 아래 형식을 따른다.

```text
<type>/<issue-number>-<description>
```

예시:

```text
feature/12-social-login
fix/24-user-lookup-condition
docs/commit-convention
```

자세한 내용은 `BRANCH_STRATEGY.md`를 확인한다.

## 커밋

커밋 메시지는 Conventional Commits 형식을 따르며, 제목은 한글로 작성한다.

```text
<type>(<scope>): <subject>
```

예시:

```text
feat(auth): 소셜 로그인 기능 추가
fix(user): 탈퇴 회원 조회 조건 수정
docs: PR 템플릿 추가
```

자세한 내용은 `COMMIT_CONVENTION.md`를 확인한다.

## Pull Request

PR 제목은 커밋 컨벤션과 같은 형식을 사용한다.
PR 본문은 `.github/pull_request_template.md`를 기준으로 작성한다.

PR 생성 전 아래 항목을 확인한다.

- [ ] 하나의 PR에 하나의 작업 단위만 담았다.
- [ ] 관련 이슈를 연결했다.
- [ ] 변경 사항과 테스트 결과를 작성했다.
- [ ] 환경변수 또는 API 변경 사항을 작성했다.
- [ ] 불필요한 로그, 주석, 임시 코드를 제거했다.

자세한 내용은 `PR_CONVENTION.md`를 확인한다.

## 이슈

이슈는 목적에 맞는 템플릿을 선택해 작성한다.

- 버그 리포트: 예상과 다른 동작이나 오류 제보
- 기능 요청: 새로운 기능 또는 개선 사항 제안
- 작업 항목: 설정, 문서, 리팩터링, 운영 작업 정리

## 환경변수

실제 비밀값은 Git에 커밋하지 않는다.
공유 가능한 변수 목록은 `.env.example`에 작성한다.

환경변수 변경이 있는 PR은 본문에 추가, 수정, 삭제 내용을 작성한다.
자세한 내용은 `ENVIRONMENT.md`를 확인한다.

## 코드 스타일

코드 스타일은 팀에서 합의한 포맷터와 린터를 기준으로 맞춘다.
도구가 정해지기 전에는 `CODE_STYLE.md`와 `NAMING_CONVENTION.md`를 기준으로 작성한다.

PR 전 아래 항목을 확인한다.

- [ ] 포맷터 또는 에디터 설정을 적용했다.
- [ ] 사용하지 않는 import, 변수, 주석, 로그를 제거했다.
- [ ] 예외 처리와 로그가 적절한지 확인했다.
- [ ] 테스트가 필요한 변경은 테스트를 추가하거나 실행 결과를 작성했다.

## 관련 문서

- `COMMIT_CONVENTION.md`: 커밋 메시지 규칙
- `BRANCH_STRATEGY.md`: 브랜치 운영 전략
- `PR_CONVENTION.md`: PR 작성 및 리뷰 규칙
- `ENVIRONMENT.md`: 환경변수 관리 규칙
- `NAMING_CONVENTION.md`: 이름 작성 규칙
- `CODE_STYLE.md`: 코드 스타일 규칙
