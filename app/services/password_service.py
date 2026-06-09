from argon2 import PasswordHasher
from argon2.exceptions import VerificationError


class PasswordService:
    def __init__(self) -> None:
        self.password_hasher = PasswordHasher()

    def hash_password(self, password: str) -> str:
        return self.password_hasher.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return self.password_hasher.verify(password_hash, password)
        except VerificationError:
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self.password_hasher.check_needs_rehash(password_hash)
