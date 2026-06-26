from dataclasses import dataclass, field
from typing import Optional

from src import layout

# Provider accent colors (R, G, B)
COLOR_CLAUDE = (255, 106, 85)
COLOR_OPENAI = (25, 195, 154)
COLOR_OPENCODE = (217, 164, 65)
COLOR_XAI = (138, 147, 163)

_VALID_SHAPES = {"quota", "capped", "spend", "balance"}


@dataclass
class Metric:
    label: str            # short tile label, e.g. "SES"
    shape: str            # one of _VALID_SHAPES — picks the renderer
    key: str              # dot-path into state, e.g. "subscription.session_pct"
    color: tuple          # RGB
    limit_key: Optional[str] = None   # capped: dot-path to the dollar limit
    reset_key: Optional[str] = None   # quota: dot-path to reset ISO timestamp
    sub_key: Optional[str] = None     # balance: dot-path to a sub-line string


@dataclass
class TilesPage:
    fixed: list                                    # list[Metric], one per fixed tile
    rotating: list = field(default_factory=list)   # list[Metric] cycled in the last tile


@dataclass
class HeroPage:
    metric: Metric


@dataclass
class Provider:
    id: str
    label: str            # full name for hero pages, e.g. "OPENCODE"
    tag: str              # 2-char abbreviation, e.g. "OC"
    color: tuple          # accent RGB
    page: object          # TilesPage | HeroPage
    enabled: bool = False


def resolve(key: str, state: dict):
    """Resolve a dot-path like 'api.total_spend' against a nested dict."""
    cur = state
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


PROVIDERS = [
    Provider(
        id="anthropic", label="CLAUDE", tag="CL", color=COLOR_CLAUDE, enabled=True,
        page=TilesPage(
            fixed=[
                Metric("SES", "quota", "subscription.session_pct", layout.COLOR_SESSION,
                       reset_key="subscription.session_reset_utc"),
                Metric("WK", "quota", "subscription.week_all_pct", layout.COLOR_WEEK_ALL,
                       reset_key="subscription.week_all_reset_utc"),
            ],
            rotating=[
                Metric("SNT", "quota", "subscription.week_sonnet_pct", layout.COLOR_WEEK_SONNET,
                       reset_key="subscription.week_sonnet_reset_utc"),
                Metric("EXT", "capped", "subscription.extra_spent", layout.COLOR_EXTRA,
                       limit_key="subscription.extra_limit"),
                Metric("API", "spend", "api.total_spend", layout.COLOR_API),
            ],
        ),
    ),
    Provider(
        id="openai", label="CHATGPT", tag="OA", color=COLOR_OPENAI, enabled=False,
        page=TilesPage(fixed=[
            Metric("GPT", "quota", "openai.quota_pct", COLOR_OPENAI,
                   reset_key="openai.quota_reset_utc"),
        ]),
    ),
    Provider(
        id="opencode", label="OPENCODE", tag="OC", color=COLOR_OPENCODE, enabled=False,
        page=HeroPage(metric=Metric("OPC", "balance", "opencode.spent_period", COLOR_OPENCODE,
                                    sub_key="opencode.autoreload")),
    ),
    Provider(
        id="xai", label="XAI", tag="XA", color=COLOR_XAI, enabled=False,
        page=HeroPage(metric=Metric("XAI", "balance", "xai.spent_period", COLOR_XAI,
                                    sub_key="xai.autoreload")),
    ),
]


def enabled_providers() -> list:
    """Providers whose pages should be shown (Phase 1: the enabled flag)."""
    return [p for p in PROVIDERS if p.enabled]
