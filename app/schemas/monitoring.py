from pydantic import BaseModel


class GeoFiles(BaseModel):
    llms_txt: bool
    llms_full_txt: bool
    sitemap_xml: bool
    robots_txt: bool


class JsonLd(BaseModel):
    local_business: bool
    faq_page: bool
    service: bool


class MonitoringSnapshot(BaseModel):
    geo_files: GeoFiles
    json_ld: JsonLd
    ssl_expiry_days: int | None = None
    response_ms: int | None = None
    pagespeed_mobile: int | None = None
    pagespeed_desktop: int | None = None
    last_measured_at: str
    from_cache: bool = False


class ResponseMsPoint(BaseModel):
    date: str
    value: int | None = None


class BotCrawls(BaseModel):
    gpt_bot: int = 0
    claude_bot: int = 0
    perplexity_bot: int = 0
    yeti: int = 0


class MonitoringHistory(BaseModel):
    response_ms_history: list[ResponseMsPoint]
    bot_crawls: BotCrawls
    bot_crawls_available: bool = False
