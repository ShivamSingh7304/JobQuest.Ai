from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password, password_hash)
    except (ValueError, TypeError):
        return False