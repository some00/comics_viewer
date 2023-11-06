from comics_viewer.in_mem_cache import InMemCache


def test_store_get():
    cache = InMemCache(10)
    cache.store("a", b"\0")
    assert cache.get("a") == b"\0"


def test_last_used_is_dropped():
    cache = InMemCache(1)
    cache.store("a", b"\0")
    cache.store("b", b"\1")
    assert cache.get("a") is None
    assert cache.get("b") == b"\1"


def test_max_size_dynamic():
    cache = InMemCache(3)
    cache.store("a", b"\0")
    cache.store("b", b"\1")
    cache.store("c", b"\2")
    cache.max_size = 2
    assert cache.get("a") is None
    assert cache.get("b") == b"\1"
    assert cache.get("c") == b"\2"


def test_fits():
    cache = InMemCache(3)
    cache.store("a", "\0")
    assert cache.fits(2)
    assert not cache.fits(3)


def test_max_size_zero():
    cache = InMemCache(0)
    cache.store("a", b"\0")
    assert cache.get("a") is None
