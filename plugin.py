from typing import Any, Optional
import asyncio
import random

from nekro_agent.api.plugin import ConfigBase, ExtraField, NekroPlugin, SandboxMethodType
from nekro_agent.api.schemas import AgentCtx
from pydantic import Field
from nekro_agent.api import core


plugin = NekroPlugin(
    name="网页转Markdown",
    module_name="nekro_html2md",
    description="访问网页链接，将HTML内容整理转换为Markdown，返回给大模型查看。",
    author="XGGM",
    version="1.0.0",
    url="https://github.com/XG2020/nekro_html2md",
)

@plugin.mount_config()
class Html2MdConfig(ConfigBase):
    keep_links: bool = Field(default=True, title="保留超链接")
    remove_scripts: bool = Field(default=True, title="移除脚本标签")
    remove_styles: bool = Field(default=True, title="移除样式标签")
    use_readability: bool = Field(default=False, title="使用 Readability 提取正文")
    collapse_whitespace: bool = Field(default=True, title="折叠空白字符")
    max_length: int = Field(default=0, title="返回内容最大长度（0为不限制）")
    user_agent: str = Field(default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36", title="User-Agent")
    accept_language: str = Field(default="zh-CN,zh;q=0.9,en;q=0.8", title="Accept-Language")
    referer: str | None = Field(default=None, title="Referer")
    retries: int = Field(default=2, title="重试次数")
    backoff_ms: int = Field(default=500, title="退避毫秒")
    delay_ms_min: int = Field(default=200, title="最小随机延迟毫秒")
    delay_ms_max: int = Field(default=1200, title="最大随机延迟毫秒")
    timeout: int = Field(default=20, title="请求超时时间秒")
    use_cloudscraper: bool = Field(default=True, title="使用Cloudscraper")

    # 以上字段将直接在插件配置页面中显示


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _get_proxy() -> Optional[str]:
    try:
        proxy = getattr(core.config, "DEFAULT_PROXY", None)
    except Exception:
        proxy = None
    if proxy:
        if isinstance(proxy, str) and proxy.startswith(("http://", "https://")):
            return proxy
        return f"http://{proxy}"
    return None


@plugin.mount_sandbox_method(
    method_type=SandboxMethodType.AGENT,
    name="fetch_html_to_markdown",
    description="抓取网页并转换为Markdown返回。参数：url(str)、keep_links(bool?)、use_readability(bool?)",
)
async def fetch_html_to_markdown(
    _ctx: AgentCtx,
    *args: Any,
    **kwargs: Any,
) -> str:
    """
    从指定URL抓取网页内容，清洗与提取后转换为Markdown并返回。
    """
    try:
        from nekro_agent.services.plugin.packages import dynamic_import_pkg
    except Exception:
        from nekro_agent.api.plugin import dynamic_import_pkg  # type: ignore

    url: str = kwargs.get("url") or (args[0] if args else "")
    if not url or not _is_url(url):
        raise ValueError("请提供有效的 http/https 网页链接参数：url")

    cfg: Html2MdConfig = getattr(plugin, "config", Html2MdConfig())
    keep_links: bool = kwargs.get("keep_links", cfg.keep_links)
    use_readability: bool = kwargs.get("use_readability", cfg.use_readability)
    remove_scripts: bool = kwargs.get("remove_scripts", cfg.remove_scripts)
    remove_styles: bool = kwargs.get("remove_styles", cfg.remove_styles)
    collapse_ws: bool = kwargs.get("collapse_whitespace", cfg.collapse_whitespace)
    ua: str = kwargs.get("user_agent", cfg.user_agent)
    al: str = kwargs.get("accept_language", cfg.accept_language)
    ref: Optional[str] = kwargs.get("referer", cfg.referer)
    retries: int = max(0, int(kwargs.get("retries", cfg.retries)))
    backoff_ms: int = max(0, int(kwargs.get("backoff_ms", cfg.backoff_ms)))
    delay_min: int = max(0, int(kwargs.get("delay_ms_min", cfg.delay_ms_min)))
    delay_max: int = max(delay_min, int(kwargs.get("delay_ms_max", cfg.delay_ms_max)))
    timeout_sec: int = max(1, int(kwargs.get("timeout", cfg.timeout)))
    use_cloudscraper: bool = bool(kwargs.get("use_cloudscraper", cfg.use_cloudscraper))

    requests = dynamic_import_pkg("requests>=2.25.0")
    bs4 = dynamic_import_pkg("beautifulsoup4>=4.9.0", import_name="bs4")

    proxy = _get_proxy()
    proxies_init = {"http": proxy, "https": proxy} if proxy else None
    ua_pool = [
        ua,
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/124.0 Safari/537.36",
    ]
    strategies = [
        (proxies_init, use_cloudscraper),
        (None, use_cloudscraper),
        (None, False),
        (proxies_init, False),
    ]
    html = ""
    last_ex: Optional[Exception] = None
    ua_idx = 0
    for strat in strategies:
        proxies = strat[0]
        use_cs = strat[1]
        headers = {
            "User-Agent": ua_pool[ua_idx % len(ua_pool)],
            "Accept-Language": al,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Connection": "keep-alive",
            "Referer": ref or url,
        }
        ua_idx += 1
        if use_cs:
            try:
                cloudscraper = dynamic_import_pkg("cloudscraper>=1.2.71")
                session = cloudscraper.create_scraper()
            except Exception:
                session = requests.Session()
        else:
            session = requests.Session()
        session.headers.update(headers)
        attempt = 0
        while True:
            if delay_max > 0:
                d = random.randint(delay_min, delay_max) / 1000.0
                await asyncio.sleep(d)
            try:
                resp = session.get(url, timeout=timeout_sec, proxies=proxies)
                code = getattr(resp, "status_code", 0)
                if code in (429, 403):
                    raise RuntimeError(f"HTTP {code}")
                resp.raise_for_status()
                html = resp.text or resp.content.decode(errors="ignore")
                if not html or "captcha" in html.lower():
                    raise RuntimeError("captcha")
                break
            except Exception as ex:
                last_ex = ex
                text = str(ex).lower()
                if proxies is not None and ("proxy" in text or "remote end closed" in text):
                    proxies = None
                    attempt = 0
                    continue
                if attempt >= retries:
                    break
                attempt += 1
                await asyncio.sleep((backoff_ms * attempt) / 1000.0)
        if html:
            break
    if not html:
        msg_lines = ["# 网页内容整理", f"- 来源: {url}", "", "抓取失败"]
        if last_ex:
            msg_lines.append(f"错误: {str(last_ex)}")
        return "\n".join(msg_lines)

    soup = bs4.BeautifulSoup(html, "lxml")
    if remove_scripts:
        for tag in soup(["script", "noscript"]):
            tag.decompose()
    if remove_styles:
        for tag in soup(["style", "link"]):
            tag.decompose()

    title = ""
    try:
        t = soup.select_one("title")
        title = (t.get_text(strip=True) if t else "") or ""
    except Exception:
        title = ""

    if use_readability:
        try:
            readability = dynamic_import_pkg("readability-lxml>=0.8.1", import_name="readability")
            from lxml.html import fromstring, tostring  # type: ignore
            doc = readability.Document(html)
            body_html = doc.summary(html_partial=True)
            # 读取原文提取的标题更准确
            if not title:
                try:
                    title = doc.short_title() or ""
                except Exception:
                    pass
            soup = bs4.BeautifulSoup(body_html, "lxml")
        except Exception:
            pass

    clean_html = str(soup)

    md_text: str = ""
    try:
        markdownify = dynamic_import_pkg("markdownify>=0.11.6", import_name="markdownify")
        md_text = markdownify.markdownify(
            clean_html,
            heading_style="ATX",
            bullets="-",
            keep_inline_images=True,
        )
    except Exception:
        html2text = dynamic_import_pkg("html2text>=2020.1.16", import_name="html2text")
        conv = html2text.HTML2Text()
        conv.ignore_links = not keep_links
        conv.body_width = 0
        conv.unicode_snob = True
        conv.wrap_links = keep_links
        conv.skip_internal_links = False
        conv.ignore_images = False
        conv.single_line_break = collapse_ws
        md_text = conv.handle(clean_html)

    if collapse_ws:
        md_text = "\n".join([line.rstrip() for line in md_text.splitlines()])

    meta_lines: list[str] = []
    if title:
        meta_lines.append(f"# {title}")
    else:
        meta_lines.append("# 网页内容整理")
    meta_lines.append(f"- 来源: {url}")
    meta = "\n".join(meta_lines) + "\n\n"
    result = meta + md_text

    max_length = int(kwargs.get("max_length", cfg.max_length or 0))
    if max_length > 0 and len(result) > max_length:
        result = result[: max_length - 3] + "..."

    return result
