import asyncio
import hashlib
import ipaddress
import socket
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .config import Settings
from .schemas import ReportRequest, SourceDocument


class SourceCollector:
    """Discovers documents, then enforces the anchor allowlist before fetching."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _domain(value: str) -> str:
        candidate = value if "://" in value else f"https://{value}"
        return (urlparse(candidate).hostname or "").lower().removeprefix("www.")

    def _anchors(self, request: ReportRequest) -> list[str]:
        values = request.anchor_sites or self.settings.anchor_domain_list
        return list(dict.fromkeys(filter(None, (self._domain(v) for v in values))))

    @staticmethod
    def _allowed(host: str, anchors: list[str]) -> bool:
        host = host.lower().removeprefix("www.")
        return any(host == anchor or host.endswith(f".{anchor}") for anchor in anchors)

    async def _is_public_host(self, host: str) -> bool:
        if self.settings.allow_private_networks:
            return True
        try:
            infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
        except socket.gaierror:
            return False
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        return True

    async def _discover(self, request: ReportRequest, anchors: list[str]) -> list[dict]:
        direct = []
        for value in request.anchor_sites:
            if value.startswith(("http://", "https://")):
                direct.append({"url": value, "title": self._domain(value), "content": ""})
        if not self.settings.tavily_api_key:
            return direct

        query = f"{request.region} {request.industry} 行业 市场 商业模式 政策 发展"
        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "include_domains": anchors,
            "max_results": self.settings.max_sources,
            "search_depth": "advanced",
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            return direct + response.json().get("results", [])

    async def _fetch(self, item: dict, anchors: list[str]) -> SourceDocument | None:
        url = str(item.get("url", ""))
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not self._allowed(host, anchors):
            return None
        if not await self._is_public_host(host):
            return None

        text = str(item.get("content", "")).strip()
        title = str(item.get("title", host)).strip()
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=False,
                headers={"User-Agent": "IndustryResearchAgent/0.1 (+research; respectful crawler)"},
            ) as client:
                current_url = url
                for _ in range(6):
                    current = urlparse(current_url)
                    current_host = (current.hostname or "").lower()
                    if (
                        current.scheme not in {"http", "https"}
                        or not self._allowed(current_host, anchors)
                        or not await self._is_public_host(current_host)
                    ):
                        return None
                    response = await client.get(current_url)
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current_url = urljoin(str(response.url), location)
                        continue
                    break
                else:
                    return None
                response.raise_for_status()
                final_host = (response.url.host or "").lower()
                if not self._allowed(final_host, anchors):
                    return None
                soup = BeautifulSoup(response.text, "html.parser")
                for node in soup(["script", "style", "nav", "footer", "noscript"]):
                    node.decompose()
                fetched = " ".join(soup.get_text(" ", strip=True).split())
                text = fetched or text
                if soup.title and soup.title.string:
                    title = soup.title.string.strip()
        except (httpx.HTTPError, UnicodeError):
            if not text:
                return None

        digest = hashlib.sha256(url.encode()).hexdigest()[:10]
        return SourceDocument(
            id=f"S-{digest}",
            title=title[:200],
            url=url,
            domain=self._domain(url),
            excerpt=text[: self.settings.max_source_chars],
            published_at=item.get("published_date"),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )

    async def collect(self, request: ReportRequest) -> list[SourceDocument]:
        anchors = self._anchors(request)
        candidates = await self._discover(request, anchors)
        results = await asyncio.gather(
            *(self._fetch(item, anchors) for item in candidates[: self.settings.max_sources]),
            return_exceptions=True,
        )
        documents = [item for item in results if isinstance(item, SourceDocument)]
        return list({doc.url: doc for doc in documents}.values())

    async def fetch_urls(self, urls: list[str]) -> list[SourceDocument]:
        """Fetch explicitly configured methodology URLs with the same network safeguards."""
        unique = list(dict.fromkeys(urls))[: self.settings.max_sources]
        anchors = list(dict.fromkeys(self._domain(url) for url in unique))
        results = await asyncio.gather(
            *(self._fetch({"url": url, "title": self._domain(url)}, anchors) for url in unique),
            return_exceptions=True,
        )
        return [item for item in results if isinstance(item, SourceDocument)]
