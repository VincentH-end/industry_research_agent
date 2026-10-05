from app.config import Settings
from app.sources import SourceCollector


def test_anchor_matches_domain_and_subdomain_only():
    collector = SourceCollector(Settings())
    assert collector._allowed("data.stats.gov.cn", ["stats.gov.cn"])
    assert collector._allowed("stats.gov.cn", ["stats.gov.cn"])
    assert not collector._allowed("stats.gov.cn.evil.example", ["stats.gov.cn"])


def test_anchor_env_is_comma_separated():
    settings = Settings(anchor_domains="stats.gov.cn, worldbank.org")
    assert settings.anchor_domain_list == ["stats.gov.cn", "worldbank.org"]

