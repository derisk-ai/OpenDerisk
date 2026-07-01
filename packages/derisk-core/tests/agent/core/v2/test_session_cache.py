from derisk.agent.core.v2.session_cache import SessionPermissionCache, hash_tool_input


def test_hash_tool_input_is_stable_and_sorted():
    h1 = hash_tool_input({"a": 1, "b": 2})
    h2 = hash_tool_input({"b": 2, "a": 1})
    assert h1 == h2
    assert len(h1) == 64  # SHA256 hex


def test_allow_session_makes_is_allowed_true():
    cache = SessionPermissionCache()
    assert cache.is_allowed("read_file", "hash1") is False
    cache.allow_session("read_file", "hash1")
    assert cache.is_allowed("read_file", "hash1") is True


def test_allow_once_does_not_cache():
    cache = SessionPermissionCache()
    cache.allow_once("read_file", "hash1")
    assert cache.is_allowed("read_file", "hash1") is False


def test_deny_revokes_prior_allow_session():
    cache = SessionPermissionCache()
    cache.allow_session("read_file", "hash1")
    assert cache.is_allowed("read_file", "hash1") is True
    cache.deny("read_file", "hash1")
    assert cache.is_allowed("read_file", "hash1") is False


def test_deny_on_uncached_is_noop():
    cache = SessionPermissionCache()
    cache.deny("read_file", "hash1")  # no error
    assert cache.is_allowed("read_file", "hash1") is False


def test_clear_wipes_all():
    cache = SessionPermissionCache()
    cache.allow_session("read_file", "hash1")
    cache.allow_session("write_file", "hash2")
    cache.clear()
    assert cache.is_allowed("read_file", "hash1") is False
    assert cache.is_allowed("write_file", "hash2") is False


def test_cache_is_per_tool_per_input():
    cache = SessionPermissionCache()
    cache.allow_session("read_file", "hash1")
    assert cache.is_allowed("read_file", "hash1") is True
    assert cache.is_allowed("read_file", "hash2") is False  # different input
    assert cache.is_allowed("write_file", "hash1") is False  # different tool
