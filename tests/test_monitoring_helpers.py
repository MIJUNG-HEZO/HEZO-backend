import pytest
from app.api.v1.monitoring import (
    _build_history_from_items,
    _extract_json_ld_types,
    _geo_files_status,
)


def test_extract_json_ld_types_finds_types():
    html = """
    <script type="application/ld+json">{"@type": "LocalBusiness"}</script>
    <script type="application/ld+json">{"@type": "FAQPage"}</script>
    """
    result = _extract_json_ld_types(html)
    assert "LocalBusiness" in result
    assert "FAQPage" in result


def test_extract_json_ld_types_empty_on_bad_html():
    result = _extract_json_ld_types("<html>no json-ld</html>")
    assert result == set()


def test_geo_files_status_all_present():
    responses = {
        "llms_txt": 200,
        "llms_full_txt": 200,
        "sitemap_xml": 200,
        "robots_txt": 200,
    }
    result = _geo_files_status(responses)
    assert result == {"llms_txt": True, "llms_full_txt": True, "sitemap_xml": True, "robots_txt": True}


def test_geo_files_status_partial():
    responses = {
        "llms_txt": 200,
        "llms_full_txt": 404,
        "sitemap_xml": 200,
        "robots_txt": 200,
    }
    result = _geo_files_status(responses)
    assert result["llms_full_txt"] is False
    assert result["llms_txt"] is True


def test_build_history_fills_missing_days():
    items = [
        {"date": "2026-06-24", "response_ms": 300},
        {"date": "2026-06-22", "response_ms": 250},
    ]
    result = _build_history_from_items(items, days=7)
    assert len(result) == 7
    dates = [r["date"] for r in result]
    assert "2026-06-24" in dates
    assert "2026-06-22" in dates
    # 없는 날은 None
    missing = next(r for r in result if r["date"] == "2026-06-23")
    assert missing["value"] is None


def test_build_history_returns_sorted_asc():
    items = [
        {"date": "2026-06-24", "response_ms": 300},
        {"date": "2026-06-20", "response_ms": 200},
    ]
    result = _build_history_from_items(items, days=7)
    dates = [r["date"] for r in result]
    assert dates == sorted(dates)
