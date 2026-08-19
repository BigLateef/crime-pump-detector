from app.core.security import (
    generate_invite_code,
    hash_invite_code,
    hash_password,
    verify_password,
)


def test_invite_code_format():
    code = generate_invite_code(9)
    assert "-" in code
    assert code.replace("-", "").isalnum()


def test_invite_codes_are_unique_across_many_calls():
    codes = {generate_invite_code(9) for _ in range(1000)}
    assert len(codes) == 1000  # no collisions in 1000 CSPRNG draws


def test_invite_code_hash_is_deterministic_and_case_insensitive():
    code = "K7M4-XP9Q"
    assert hash_invite_code(code) == hash_invite_code("k7m4-xp9q")
    assert hash_invite_code(code) == hash_invite_code("K7M4XP9Q")


def test_password_hash_roundtrip():
    hashed = hash_password("a-fairly-long-passphrase")
    assert verify_password("a-fairly-long-passphrase", hashed) is True
    assert verify_password("wrong-passphrase", hashed) is False


def test_ambiguous_characters_excluded_from_invite_alphabet():
    codes = "".join(generate_invite_code(20) for _ in range(50))
    for ambiguous_char in "0O1IL":
        assert ambiguous_char not in codes.replace("-", "")
