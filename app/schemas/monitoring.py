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


class LlmsFullQuality(BaseModel):
    faq_count: int = 0
    char_count: int = 0
    has_core_services: bool = False
    has_faq: bool = False
    has_core_pages: bool = False


class MonitoringSnapshot(BaseModel):
    geo_files: GeoFiles
    json_ld: JsonLd
    ssl_expiry_days: int | None = None
    response_ms: int | None = None
    pagespeed_mobile: int | None = None
    pagespeed_desktop: int | None = None
    llms_full_quality: LlmsFullQuality | None = None
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


class ScorePoint(BaseModel):
    date: str
    score: int
    delta: int = 0


class ActionItem(BaseModel):
    level: str   # "red" | "yellow" | "green"
    text: str


class ScoreHistory(BaseModel):
    score_history: list[ScorePoint]
    latest_score: int | None = None
    latest_delta: int = 0
    action_items: list[ActionItem] = []
    geo_file_score: int | None = None


class LlmCitationRates(BaseModel):
    claude: float | None = None
    chatgpt: float | None = None
    perplexity: float | None = None
    naver: float | None = None


class CitationPoint(BaseModel):
    date: str
    rates: LlmCitationRates


class CitationHistory(BaseModel):
    citation_history: list[CitationPoint]
    latest: LlmCitationRates | None = None
    query_count: int = 0


class InfraMetrics(BaseModel):
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float | None = None
    net_rx_kbps: float | None = None
    net_tx_kbps: float | None = None
    available: bool = False
