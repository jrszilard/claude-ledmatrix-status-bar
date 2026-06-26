from src import registry


def test_resolve_nested():
    state = {"api": {"total_spend": 12.47}}
    assert registry.resolve("api.total_spend", state) == 12.47


def test_resolve_missing_returns_none():
    assert registry.resolve("api.nope", {"api": {}}) is None
    assert registry.resolve("x.y.z", {}) is None
    assert registry.resolve("a.b", {"a": 5}) is None  # non-dict mid-path


def test_only_anthropic_enabled_by_default():
    assert [p.id for p in registry.enabled_providers()] == ["anthropic"]


def test_claude_page_two_fixed_three_rotating():
    claude = next(p for p in registry.PROVIDERS if p.id == "anthropic")
    assert isinstance(claude.page, registry.TilesPage)
    assert [m.label for m in claude.page.fixed] == ["SES", "WK"]
    assert [m.label for m in claude.page.rotating] == ["SNT", "EXT", "API"]


def test_balance_providers_use_hero_pages():
    for pid in ("opencode", "xai"):
        p = next(pp for pp in registry.PROVIDERS if pp.id == pid)
        assert isinstance(p.page, registry.HeroPage)
        assert p.page.metric.shape == "balance"


def test_every_metric_has_valid_shape():
    valid = {"quota", "capped", "spend", "balance"}
    for p in registry.PROVIDERS:
        metrics = (
            p.page.fixed + p.page.rotating
            if isinstance(p.page, registry.TilesPage)
            else [p.page.metric]
        )
        for m in metrics:
            assert m.shape in valid
