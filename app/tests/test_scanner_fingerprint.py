"""
Tests app.workers.scanner._fingerprint directly, without importing the
full scanner module (which pulls in sqlalchemy/redis at import time,
unavailable in this sandbox). Same AST-extraction technique as
test_loader.py — loads just the one pure function's source and execs it
in isolation.
"""
import ast
import types


def _load_fingerprint_fn():
    with open("app/workers/scanner.py") as f:
        source = f.read()
    tree = ast.parse(source)
    keep_nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_fingerprint"
    ]
    # _fingerprint only needs hashlib, imported at module top in the real
    # file - include that import explicitly since we're not exec'ing the
    # whole module.
    import_node = ast.parse("import hashlib").body[0]
    module = types.ModuleType("fingerprint_shim")
    code = compile(ast.Module(body=[import_node] + keep_nodes, type_ignores=[]), "<fingerprint_shim>", "exec")
    exec(code, module.__dict__)
    return module._fingerprint


_fingerprint = _load_fingerprint_fn()


def test_fingerprint_is_deterministic():
    a = _fingerprint("token-1", "EARLY", 60)
    b = _fingerprint("token-1", "EARLY", 60)
    assert a == b


def test_fingerprint_differs_by_token():
    a = _fingerprint("token-1", "EARLY", 60)
    b = _fingerprint("token-2", "EARLY", 60)
    assert a != b


def test_fingerprint_differs_by_signal_level():
    a = _fingerprint("token-1", "EARLY", 60)
    b = _fingerprint("token-1", "WATCH", 60)
    assert a != b


def test_fingerprint_buckets_nearby_scores_together():
    # 58, 60, 61 should all round to the same bucket of 5 (60), so a
    # near-identical re-score within a cooldown window is still treated
    # as a duplicate - this is the whole point of the bucketing.
    a = _fingerprint("token-1", "EARLY", 58)
    b = _fingerprint("token-1", "EARLY", 60)
    c = _fingerprint("token-1", "EARLY", 61)
    assert a == b == c


def test_fingerprint_does_not_bucket_scores_in_different_buckets():
    a = _fingerprint("token-1", "EARLY", 55)
    b = _fingerprint("token-1", "EARLY", 65)
    assert a != b


def test_fingerprint_is_a_valid_sha256_hex_digest():
    fp = _fingerprint("token-1", "EARLY", 60)
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)
