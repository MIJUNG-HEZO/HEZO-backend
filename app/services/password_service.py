from argon2 import PasswordHasher


class PasswordService:
    def __init__(self) -> None:
        self.password_hasher = PasswordHasher()

    def hash_password(self, password: str) -> str:
        return self.password_hasher.hash(password)
