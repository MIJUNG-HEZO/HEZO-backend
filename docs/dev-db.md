# 개발 DB 접속 가이드

현재 개발용 PostgreSQL 데이터베이스는 EC2 Ubuntu 서버에서 실행한다.
PostgreSQL은 서버 내부의 `localhost:5432`에만 열려 있으므로, 로컬 개발에서는 SSH 터널을 사용한다.

## SSH 터널 실행

```bash
ssh -i ~/Downloads/hezo-dev-db.pem -N -L 15432:localhost:5432 ubuntu@43.200.163.128
```

백엔드를 로컬에서 실행하거나 VSCode DB 플러그인으로 접속하는 동안 이 터미널은 닫지 않는다.

## 로컬 `.env` 설정

`.env.example`을 `.env`로 복사한 뒤 비밀번호만 실제 값으로 바꾼다.

```env
DATABASE_URL=postgresql+psycopg://hezo_app:<password>@localhost:15432/hezo_dev
```

`.env`와 실제 DB 접속 정보는 커밋하지 않는다.

## DB 접속 정보 확인

개발 DB 접속 정보 파일은 EC2 서버에 저장되어 있다.

```bash
ssh -i ~/Downloads/hezo-dev-db.pem ubuntu@43.200.163.128 'cat ~/hezo-db-credentials.txt'
```

비밀번호는 팀에서 정한 비공개 채널로만 공유한다.

## VSCode DB 플러그인 설정

SSH 터널을 먼저 실행한 뒤, VSCode DB 플러그인에는 아래 값을 입력한다.

```text
서버 유형: PostgreSQL
호스트: 127.0.0.1
포트: 15432
사용자 이름: hezo_app
비밀번호: 실제 DB 비밀번호
데이터베이스: hezo_dev
SSL: off
```

플러그인 자체의 SSH 터널 기능은 사용하지 않는다. 터미널에서 직접 연 SSH 터널을 사용한다.

## 연결 스모크 체크

SSH 터널을 실행한 상태에서 아래 명령을 실행한다.

```bash
python - <<'PY'
import asyncio

from app.db.session import check_database_connection

print(asyncio.run(check_database_connection()))
PY
```

기대 결과:

```text
True
```

## 마이그레이션 실행

SSH 터널을 실행하고 `.env`의 `DATABASE_URL`이 `localhost:15432`를 바라보는지 확인한 뒤 실행한다.
처음 실행하거나 `uv.lock`이 변경된 경우 먼저 개발 의존성을 동기화한다.

```bash
uv sync --dev
```

마이그레이션을 최신 revision까지 적용한다.

```bash
uv run alembic upgrade head
```

현재 적용된 revision은 아래 명령으로 확인한다.

```bash
uv run alembic current
```

직전 migration을 되돌려야 할 때는 아래 명령을 사용한다.

```bash
uv run alembic downgrade -1
```

## 주의 사항

- EC2 보안그룹에서 PostgreSQL `5432` 포트를 전체 공개하지 않는다.
- 로컬에서 DB에 붙을 때는 항상 SSH 터널을 먼저 실행한다.
- `DATABASE_URL`의 호스트는 `43.200.163.128`이 아니라 `localhost` 또는 `127.0.0.1`이다.
- 로컬 터널 포트는 `15432`, 서버 내부 PostgreSQL 포트는 `5432`다.
- 실제 비밀번호, JWT secret, OAuth secret은 GitHub 이슈, PR, 문서, 코드에 남기지 않는다.
