# 네이밍 컨벤션

이 문서는 프로젝트 전반에서 사용하는 이름 작성 규칙을 정의한다.
이름은 코드의 의도를 드러내는 가장 가까운 문서이므로, 일관성과 명확성을 우선한다.

## 기본 원칙

1. 이름은 역할과 의도가 드러나게 작성한다.
2. 줄임말은 팀에서 합의된 경우에만 사용한다.
3. 같은 개념은 프로젝트 전체에서 같은 이름으로 표현한다.
4. 불필요하게 넓은 이름은 피한다.
5. 타입이나 자료구조보다 도메인 의미를 우선한다.
6. Boolean 이름은 참/거짓 의미가 자연스럽게 읽히도록 작성한다.
7. 단수와 복수를 구분해 사용한다.
8. 숫자, 임시 표현, 모호한 이름은 피한다.
9. 외부 API, 라이브러리, 프레임워크가 요구하는 이름은 해당 규칙을 따른다.
10. 이름 변경 범위가 큰 경우 PR에서 변경 의도와 영향 범위를 설명한다.

## 공통 표기법

| 표기법 | 예시 | 사용 위치 |
| --- | --- | --- |
| `camelCase` | `userName` | 변수, 함수, 메서드 |
| `PascalCase` | `UserService` | 클래스, 타입, enum |
| `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT` | 상수, 환경변수 |
| `snake_case` | `user_name` | DB 컬럼, 파일 일부 |
| `kebab-case` | `user-profile` | URL path, 브랜치명, 일부 파일명 |

## 패키지 / 모듈

패키지와 모듈 이름은 소문자로 작성한다.
여러 단어가 필요한 경우 언어와 프레임워크 관례를 따른다.

권장:

```text
auth
user
order
payment
notification
```

피하기:

```text
Auth
userModule
commonUtils
```

규칙:

1. 도메인 기준으로 이름을 정한다.
2. 너무 넓은 `common`, `util`, `helper`는 남용하지 않는다.
3. 공통 모듈은 역할이 드러나도록 세분화한다.
4. 복수 도메인을 억지로 하나의 패키지에 넣지 않는다.

예시:

```text
auth
auth.token
auth.oauth
user
user.profile
payment
payment.history
```

## 클래스 / 타입

클래스와 타입 이름은 `PascalCase`를 사용한다.
이름은 명사 또는 명사구로 작성한다.

권장:

```text
User
UserService
UserRepository
CreateUserRequest
UserResponse
PaymentHistory
JwtTokenProvider
```

피하기:

```text
UserManager
UserUtil
DataInfo
ProcessUser
```

규칙:

1. 역할이 분명한 suffix를 사용한다.
2. `Manager`, `Processor`, `Util`, `Helper`는 역할이 모호하면 사용하지 않는다.
3. 요청 DTO는 `Request`, 응답 DTO는 `Response` suffix를 사용한다.
4. 명령성 객체는 `Command`, 조회 조건은 `Query` 또는 `Condition`을 사용한다.
5. 예외 클래스는 `Exception` suffix를 사용한다.

권장 suffix:

| Suffix | 용도 |
| --- | --- |
| `Controller` | HTTP 요청 처리 |
| `Service` | 비즈니스 로직 |
| `Repository` | 데이터 접근 |
| `Request` | 요청 DTO |
| `Response` | 응답 DTO |
| `Command` | 변경 작업 입력 |
| `Query` | 조회 작업 입력 |
| `Event` | 도메인 또는 시스템 이벤트 |
| `Exception` | 예외 |
| `Config` | 설정 |
| `Provider` | 특정 값 또는 기능 제공 |
| `Validator` | 검증 |
| `Mapper` | 객체 변환 |

## 함수 / 메서드

함수와 메서드는 `camelCase`를 사용한다.
이름은 동사 또는 동사구로 작성한다.

권장:

```text
createUser
findUserById
updateProfile
deleteRefreshToken
validatePassword
sendVerificationEmail
```

피하기:

```text
user
userData
process
handle
doSomething
```

규칙:

1. 메서드 이름만 보고 주요 동작을 알 수 있어야 한다.
2. 조회 메서드는 `find`, `get`, `search`, `exists`, `count`를 구분한다.
3. 생성은 `create`, 수정은 `update`, 삭제는 `delete`를 사용한다.
4. 검증은 `validate`, 변환은 `to` 또는 `map`을 사용한다.
5. 단순 이벤트 처리는 `handle`을 사용할 수 있으나 대상 이벤트를 함께 적는다.

조회 prefix 기준:

| Prefix | 의미 |
| --- | --- |
| `find` | 없을 수 있는 단건 또는 목록 조회 |
| `get` | 반드시 존재해야 하는 값 조회 |
| `search` | 조건 기반 검색 |
| `exists` | 존재 여부 확인 |
| `count` | 개수 조회 |

예시:

```text
findUserByEmail
getUserById
searchOrders
existsUserByNickname
countActiveUsers
```

## 변수

변수는 `camelCase`를 사용한다.
이름은 저장된 값의 의미가 드러나게 작성한다.

권장:

```text
userId
accessToken
refreshToken
orderItems
expiredAt
isDeleted
```

피하기:

```text
data
info
temp
str
list
flag
```

규칙:

1. 단건은 단수, 목록은 복수를 사용한다.
2. 컬렉션은 의미 있는 복수 명사를 사용한다.
3. 임시 변수라도 의미 있는 이름을 사용한다.
4. 타입이 아니라 도메인 의미를 이름에 담는다.
5. 짧은 범위의 반복 변수는 `i`, `j`를 허용한다.

## Boolean

Boolean 이름은 참일 때 자연스럽게 읽히도록 작성한다.

권장 prefix:

| Prefix | 예시 | 의미 |
| --- | --- | --- |
| `is` | `isDeleted` | 상태 |
| `has` | `hasPermission` | 보유 여부 |
| `can` | `canUpdate` | 가능 여부 |
| `should` | `shouldRetry` | 조건 판단 |
| `use` | `useCache` | 사용 여부 |

피하기:

```text
deleteFlag
status
check
notFound
```

부정형 이름은 가능한 한 피한다.

권장:

```text
isActive
```

피하기:

```text
isNotDeleted
```

## 상수

상수는 `UPPER_SNAKE_CASE`를 사용한다.

예시:

```text
MAX_RETRY_COUNT
DEFAULT_PAGE_SIZE
ACCESS_TOKEN_EXPIRES_IN
PASSWORD_MIN_LENGTH
```

규칙:

1. 매직 넘버와 매직 문자열은 상수로 분리한다.
2. 상수 이름에는 값보다 의미를 담는다.
3. 단위가 중요한 값은 이름에 단위를 포함한다.

예시:

```text
TOKEN_EXPIRES_IN_SECONDS
REQUEST_TIMEOUT_MILLIS
```

## Enum

Enum 타입은 `PascalCase`, enum 값은 사용하는 언어 관례를 따른다.
별도 관례가 없다면 enum 값은 `UPPER_SNAKE_CASE`를 권장한다.

예시:

```text
UserRole
USER
ADMIN
```

```text
OrderStatus
PENDING
PAID
CANCELED
```

규칙:

1. enum 타입 이름은 단수 명사로 작성한다.
2. enum 값은 상태나 역할이 명확히 드러나게 작성한다.
3. `NORMAL`, `DEFAULT`, `ETC`처럼 의미가 흐린 값은 피한다.

## 파일명

파일명은 사용하는 언어와 프레임워크 관례를 우선한다.

일반 규칙:

1. 클래스 기반 파일은 클래스명과 동일하게 작성한다.
2. 설정 파일은 역할이 드러나게 작성한다.
3. 문서 파일은 대문자 스네이크 케이스 또는 kebab-case 중 프로젝트 내 일관된 방식을 따른다.

예시:

```text
UserService.java
UserController.java
application.yml
docker-compose.yml
COMMIT_CONVENTION.md
```

## API URL

API URL은 소문자 kebab-case를 사용한다.
리소스는 명사로 표현하고, 동사는 HTTP Method로 표현한다.

권장:

```text
GET /api/users
GET /api/users/{userId}
POST /api/users
PATCH /api/users/{userId}
DELETE /api/users/{userId}
```

피하기:

```text
GET /api/getUsers
POST /api/user/create
PATCH /api/update-user
```

규칙:

1. URL path에는 동사를 사용하지 않는다.
2. 리소스 이름은 복수형을 사용한다.
3. path variable은 `camelCase`를 사용한다.
4. query parameter는 `camelCase`를 사용한다.
5. 하위 리소스는 계층 구조로 표현한다.

예시:

```text
GET /api/users/{userId}/orders
GET /api/orders?orderStatus=PAID
```

## DTO 필드

요청/응답 필드는 `camelCase`를 사용한다.

예시:

```json
{
  "userId": 1,
  "nickname": "hezo",
  "profileImageUrl": "https://example.com/profile.png",
  "createdAt": "2026-06-06T10:00:00"
}
```

규칙:

1. API 응답 필드는 프론트엔드와 합의된 이름을 유지한다.
2. 날짜/시간 필드는 `At`, 날짜만 의미하면 `Date` suffix를 사용한다.
3. URL 값은 `Url` suffix를 사용한다.
4. ID 값은 `Id` suffix를 사용한다.

예시:

```text
createdAt
updatedAt
deletedAt
birthDate
profileImageUrl
userId
```

## 데이터베이스

DB 테이블과 컬럼은 `snake_case`를 사용한다.

테이블:

```text
users
orders
order_items
payment_histories
```

컬럼:

```text
id
user_id
order_id
created_at
updated_at
deleted_at
```

규칙:

1. 테이블 이름은 복수형을 사용한다.
2. 컬럼 이름은 소문자 snake_case를 사용한다.
3. 외래키는 `<참조_테이블_단수>_id` 형식을 사용한다.
4. 생성/수정/삭제 시간은 `created_at`, `updated_at`, `deleted_at`을 사용한다.
5. Boolean 컬럼은 `is_`, `has_`, `can_` prefix를 사용한다.

예시:

```text
is_deleted
is_active
has_agreed_terms
can_receive_notification
```

## 테스트

테스트 이름은 검증하려는 동작과 기대 결과가 드러나게 작성한다.
사용하는 테스트 프레임워크 관례에 맞게 한글 또는 영어를 선택하되, 한 파일 안에서는 일관성을 유지한다.

권장:

```text
회원가입_성공
중복된_이메일이면_회원가입에_실패한다
createUserSuccess
failToCreateUserWhenEmailDuplicated
```

규칙:

1. 테스트 이름에는 조건과 기대 결과를 포함한다.
2. 구현 세부사항보다 사용자 관점의 동작을 표현한다.
3. 같은 테스트 파일 안에서는 한글/영어 방식을 섞지 않는다.

## 피해야 할 이름

아래 이름은 의미가 모호하므로 가능한 한 사용하지 않는다.

```text
data
info
temp
tmp
obj
val
str
num
list
map
flag
result
manager
helper
util
common
process
handle
doSomething
```

단, 짧은 범위에서 관례적으로 쓰는 경우는 허용한다.

예시:

```text
for (int i = 0; i < size; i++)
```

## 이름 변경 기준

아래 경우에는 이름 변경을 고려한다.

1. 이름만 보고 역할을 알기 어렵다.
2. 실제 동작과 이름이 다르다.
3. 같은 개념을 여러 이름으로 부르고 있다.
4. 도메인 용어가 변경되었다.
5. 변수나 함수의 책임이 커져 기존 이름이 맞지 않는다.

## PR 작성 시 네이밍 변경 공유

네이밍 변경 범위가 큰 PR은 아래 내용을 본문에 작성한다.

```markdown
## 구현 내용
- userAccount 용어를 member로 통일
- DB 컬럼 `user_name`을 `nickname`으로 변경

## 리뷰 요청 사항
- 변경된 도메인 용어가 API 응답과 DB 컬럼에 일관되게 반영되었는지 확인 부탁드립니다.
```

## 다음에 정할 문서 후보

네이밍 컨벤션과 함께 아래 문서를 추가하는 것을 권장한다.

- `CODE_STYLE.md`: 포맷터, 린터, import 정렬, 예외 처리 규칙
