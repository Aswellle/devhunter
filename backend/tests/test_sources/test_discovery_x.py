"""
tests/test_sources/test_discovery_x.py
X（推特）账号主页在自动发现/预览流程中的识别测试。
"""
from app.crawler.engine import CrawlItem, CrawlResult
from app.crawler.templates import get_template, list_templates
from app.sources.discovery import DiscoveryResult, url_discoverer
from app.sources import preview as preview_module


class TestXTemplate:
    def test_built_in_x_templates_are_discussion_sources(self):
        expected = {"x_world", "x_chinese", "x_tech", "x_dev"}
        available = {t.id for t in list_templates()}
        assert expected <= available

        template = get_template("x_world")
        assert template is not None
        assert template.source_url == "https://x.com/BBCWorld"
        assert template.selector_list.startswith("x:")
        assert template.content_kind == "discussion"
        assert template.recommended_cron


class TestDiscoverXProfile:
    def test_x_profile_short_circuits_without_fetching_spa(self):
        result = url_discoverer.discover("x.com/BBCWorld")
        assert result.failure is None
        assert result.source_type == "x"
        assert result.list_selector == "x:"
        assert result.title_selector == "x:text"
        assert result.link_selector == "x:url"
        assert result.summary_selector == "x:meta"
        assert "@BBCWorld" in result.title

    def test_syndication_url_is_also_recognized(self):
        result = url_discoverer.discover(
            "https://syndication.twitter.com/srv/timeline-profile/screen-name/OpenAI"
        )
        assert result.source_type == "x"
        assert "@OpenAI" in result.title

    def test_tweet_detail_url_is_not_treated_as_timeline(self):
        result = url_discoverer.discover("https://x.com/BBCWorld/status/123")
        # 不是账号主页：仍然走普通发现流程，最终应以失败/非 x 类型结束，
        # 绝不能把推文详情页当成账号时间线
        assert result.source_type != "x"


class TestPreviewX:
    def test_preview_x_passes_x_selectors_to_engine(self, monkeypatch):
        captured: dict = {}

        def fake_fetch(url, selectors, keywords):
            captured["url"] = url
            captured["selectors"] = selectors
            return CrawlResult(
                items=[CrawlItem(
                    title="hello",
                    url="https://x.com/BBCWorld/status/1",
                    summary="@BBCWorld",
                )],
                http_status=200,
                extracted_count=1,
            )

        monkeypatch.setattr(preview_module, "fetch_and_parse", fake_fetch)
        result = preview_module.preview_extractor.preview(
            "https://x.com/BBCWorld",
            DiscoveryResult(url="https://x.com/BBCWorld", source_type="x"),
            limit=3,
        )

        assert result.success is True
        assert captured["selectors"] == {
            "list": "x:",
            "title": "x:text",
            "link": "x:url",
            "summary": "x:meta",
        }
        assert result.items[0]["url"] == "https://x.com/BBCWorld/status/1"
