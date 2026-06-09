import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, get_user_service, require_authenticated
from app.core import error_codes
from app.core.exceptions import AppException
from app.main import app
from app.schemas.user import UserResponse, UserUpdateRequest
from app.services.user_service import UserService


class FakeUserService:
    def __init__(self) -> None:
        self.requested_user_id: UUID | None = None
        self.updated_user_id: UUID | None = None
        self.update_payload: UserUpdateRequest | None = None

    async def get_me(self, *, user_id: UUID) -> UserResponse:
        self.requested_user_id = user_id
        return UserResponse(
            id=user_id,
            email="user@example.com",
            name="홍길동",
            phone="010-1234-5678",
            email_verified_at=datetime(2026, 6, 9, tzinfo=UTC),
            email_verified=True,
            created_at=datetime(2026, 6, 8, tzinfo=UTC),
            updated_at=datetime(2026, 6, 9, tzinfo=UTC),
        )

    async def update_me(self, *, user_id: UUID, payload: UserUpdateRequest) -> UserResponse:
        self.updated_user_id = user_id
        self.update_payload = payload
        return UserResponse(
            id=user_id,
            email="user@example.com",
            name=payload.name or "홍길동",
            phone=payload.phone,
            email_verified_at=datetime(2026, 6, 9, tzinfo=UTC),
            email_verified=True,
            created_at=datetime(2026, 6, 8, tzinfo=UTC),
            updated_at=datetime(2026, 6, 9, 1, tzinfo=UTC),
        )


class FakeUserRepository:
    def __init__(self, user: SimpleNamespace | None) -> None:
        self.user = user
        self.updated_kwargs: dict[str, object] | None = None

    async def get_by_id(self, user_id: UUID) -> SimpleNamespace | None:
        if self.user is not None:
            self.user.requested_user_id = user_id
        return self.user

    async def get_by_id_for_update(self, user_id: UUID) -> SimpleNamespace | None:
        if self.user is not None:
            self.user.requested_user_id = user_id
        return self.user

    async def update_profile(
        self,
        *,
        user: SimpleNamespace,
        name: str,
        phone: str | None,
    ) -> SimpleNamespace:
        self.updated_kwargs = {
            "user": user,
            "name": name,
            "phone": phone,
        }
        user.name = name
        user.phone = phone
        return user


class FakeAsyncSession:
    def __init__(self) -> None:
        self.committed = False
        self.refreshed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _: SimpleNamespace) -> None:
        self.refreshed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def make_user(*, deleted_at: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        name="홍길동",
        phone=None,
        email_verified_at=datetime(2026, 6, 9, tzinfo=UTC),
        created_at=datetime(2026, 6, 8, tzinfo=UTC),
        updated_at=datetime(2026, 6, 9, tzinfo=UTC),
        deleted_at=deleted_at,
    )


def test_get_me_returns_current_user_profile() -> None:
    client = TestClient(app)
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime(2026, 6, 9, tzinfo=UTC))
    fake_user_service = FakeUserService()
    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_user_service] = lambda: fake_user_service

    try:
        response = client.get("/api/v1/users/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(current_user.id)
    assert body["email"] == "user@example.com"
    assert body["name"] == "홍길동"
    assert body["phone"] == "010-1234-5678"
    assert body["email_verified"] is True
    assert fake_user_service.requested_user_id == current_user.id


def test_update_me_updates_current_user_profile() -> None:
    client = TestClient(app)
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime(2026, 6, 9, tzinfo=UTC))
    fake_user_service = FakeUserService()
    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_user_service] = lambda: fake_user_service

    try:
        response = client.patch(
            "/api/v1/users/me",
            json={
                "name": "Kim Hezo",
                "phone": "010-1111-2222",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(current_user.id)
    assert body["name"] == "Kim Hezo"
    assert body["phone"] == "010-1111-2222"
    assert fake_user_service.updated_user_id == current_user.id
    assert fake_user_service.update_payload == UserUpdateRequest(
        name="Kim Hezo",
        phone="010-1111-2222",
    )


def test_update_me_rejects_invalid_name() -> None:
    client = TestClient(app)
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime(2026, 6, 9, tzinfo=UTC))
    app.dependency_overrides[require_authenticated] = lambda: current_user

    try:
        response = client.patch(
            "/api/v1/users/me",
            json={
                "name": "홍길동123",
                "phone": "010-1111-2222",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_update_me_rejects_invalid_phone() -> None:
    client = TestClient(app)
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime(2026, 6, 9, tzinfo=UTC))
    app.dependency_overrides[require_authenticated] = lambda: current_user

    try:
        response = client.patch(
            "/api/v1/users/me",
            json={
                "name": "홍길동",
                "phone": "not-a-phone",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_update_me_rejects_phone_with_tab_or_newline() -> None:
    client = TestClient(app)
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime(2026, 6, 9, tzinfo=UTC))
    app.dependency_overrides[require_authenticated] = lambda: current_user

    try:
        response = client.patch(
            "/api/v1/users/me",
            json={
                "name": "홍길동",
                "phone": "010\t1234\n5678",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_update_me_allows_phone_only_patch() -> None:
    client = TestClient(app)
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime(2026, 6, 9, tzinfo=UTC))
    fake_user_service = FakeUserService()
    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_user_service] = lambda: fake_user_service

    try:
        response = client.patch(
            "/api/v1/users/me",
            json={
                "phone": "010-1111-2222",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["name"] == "홍길동"
    assert fake_user_service.update_payload == UserUpdateRequest(phone="010-1111-2222")


def test_update_me_rejects_consecutive_spaces_in_name() -> None:
    client = TestClient(app)
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime(2026, 6, 9, tzinfo=UTC))
    app.dependency_overrides[require_authenticated] = lambda: current_user

    try:
        response = client.patch(
            "/api/v1/users/me",
            json={
                "name": "Kim  Hezo",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_user_service_get_me_returns_email_verified_flag() -> None:
    async def run_service() -> None:
        session = FakeAsyncSession()
        user = make_user()
        service = UserService(session)  # type: ignore[arg-type]
        service.user_repository = FakeUserRepository(user)  # type: ignore[assignment]

        response = await service.get_me(user_id=user.id)

        assert response.id == user.id
        assert response.email == user.email
        assert response.email_verified is True

    asyncio.run(run_service())


def test_user_service_get_me_rejects_missing_user() -> None:
    async def run_service() -> None:
        session = FakeAsyncSession()
        service = UserService(session)  # type: ignore[arg-type]
        service.user_repository = FakeUserRepository(None)  # type: ignore[assignment]

        with pytest.raises(AppException) as exc_info:
            await service.get_me(user_id=uuid4())

        assert exc_info.value.code == error_codes.USER_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_service())


def test_user_service_update_me_updates_name_and_phone() -> None:
    async def run_service() -> None:
        session = FakeAsyncSession()
        user = make_user()
        repository = FakeUserRepository(user)
        service = UserService(session)  # type: ignore[arg-type]
        service.user_repository = repository  # type: ignore[assignment]

        response = await service.update_me(
            user_id=user.id,
            payload=UserUpdateRequest(name="Kim Hezo", phone="010-1111-2222"),
        )

        assert repository.updated_kwargs == {
            "user": user,
            "name": "Kim Hezo",
            "phone": "010-1111-2222",
        }
        assert response.name == "Kim Hezo"
        assert response.phone == "010-1111-2222"
        assert session.committed is True
        assert session.refreshed is True

    asyncio.run(run_service())


def test_user_service_update_me_returns_without_write_when_payload_is_empty() -> None:
    async def run_service() -> None:
        session = FakeAsyncSession()
        user = make_user()
        repository = FakeUserRepository(user)
        service = UserService(session)  # type: ignore[arg-type]
        service.user_repository = repository  # type: ignore[assignment]

        response = await service.update_me(
            user_id=user.id,
            payload=UserUpdateRequest(),
        )

        assert repository.updated_kwargs is None
        assert response.name == user.name
        assert response.phone == user.phone
        assert session.committed is False
        assert session.refreshed is False

    asyncio.run(run_service())


def test_user_service_update_me_preserves_omitted_name() -> None:
    async def run_service() -> None:
        session = FakeAsyncSession()
        user = make_user()
        user.phone = "010-0000-0000"
        repository = FakeUserRepository(user)
        service = UserService(session)  # type: ignore[arg-type]
        service.user_repository = repository  # type: ignore[assignment]

        response = await service.update_me(
            user_id=user.id,
            payload=UserUpdateRequest(phone="010-1111-2222"),
        )

        assert repository.updated_kwargs == {
            "user": user,
            "name": "홍길동",
            "phone": "010-1111-2222",
        }
        assert response.name == "홍길동"
        assert response.phone == "010-1111-2222"

    asyncio.run(run_service())


def test_user_service_update_me_clears_phone_when_null_is_sent() -> None:
    async def run_service() -> None:
        session = FakeAsyncSession()
        user = make_user()
        user.phone = "010-0000-0000"
        repository = FakeUserRepository(user)
        service = UserService(session)  # type: ignore[arg-type]
        service.user_repository = repository  # type: ignore[assignment]

        response = await service.update_me(
            user_id=user.id,
            payload=UserUpdateRequest(name="홍길동", phone=None),
        )

        assert repository.updated_kwargs == {
            "user": user,
            "name": "홍길동",
            "phone": None,
        }
        assert response.phone is None

    asyncio.run(run_service())


def test_user_service_update_me_preserves_phone_when_omitted() -> None:
    async def run_service() -> None:
        session = FakeAsyncSession()
        user = make_user()
        user.phone = "010-0000-0000"
        repository = FakeUserRepository(user)
        service = UserService(session)  # type: ignore[arg-type]
        service.user_repository = repository  # type: ignore[assignment]

        response = await service.update_me(
            user_id=user.id,
            payload=UserUpdateRequest(name="Kim Hezo"),
        )

        assert repository.updated_kwargs == {
            "user": user,
            "name": "Kim Hezo",
            "phone": "010-0000-0000",
        }
        assert response.phone == "010-0000-0000"

    asyncio.run(run_service())


def test_user_service_update_me_rejects_deleted_user() -> None:
    async def run_service() -> None:
        session = FakeAsyncSession()
        service = UserService(session)  # type: ignore[arg-type]
        service.user_repository = FakeUserRepository(  # type: ignore[assignment]
            make_user(deleted_at=datetime(2026, 6, 9, tzinfo=UTC))
        )

        with pytest.raises(AppException) as exc_info:
            await service.update_me(
                user_id=uuid4(),
                payload=UserUpdateRequest(name="홍길동", phone=None),
            )

        assert exc_info.value.code == error_codes.USER_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_service())
