"""
网页抓取解析器 - 从 MCP 目录站点的 HTML 中提取搜索结果

功能简述:
    提供 mcp.so、mcp.aibase.cn、mcpmarket.cn 等网页抓取源的 HTML 解析函数。
    每个解析器将 HTML 转换为统一的 SearchResult 字典列表。

主要函数清单:
    - parse_mcp_so_html: 解析 mcp.so 搜索页 HTML
    - parse_mcp_aibase_html: 解析 mcp.aibase.cn 搜索页 HTML
    - parse_mcpmarket_html: 解析 mcpmarket.cn 搜索页 HTML

使用示例:
    results = parse_mcp_so_html(html_text)
    for r in results:
        print(r["name"], r["plugin_type"])
"""

from __future__ import annotations

import contextlib
from typing import Any

from bs4 import BeautifulSoup


def parse_mcp_so_html(html: str) -> list[dict[str, Any]]:
    """
    解析 mcp.so 搜索页 HTML。

    从搜索结果卡片中提取名称、描述、标签等信息，
    并尝试从页面内容判断 plugin_type（skill / mcp_server）。

    Args:
        html: 搜索页的 HTML 文本

    Returns:
        搜索结果字典列表
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []

    # mcp.so 的搜索结果通常位于卡片容器中
    cards = soup.select("a[href^='/server/'], a[href^='/skill/']") or soup.select(
        ".server-card, .skill-card, [class*='card']"
    )

    for card in cards:
        name_el = card.select_one("h3, h2, .name, [class*='title']")
        desc_el = card.select_one("p, .description, [class*='desc']")

        if not name_el:
            continue

        from bs4 import Tag

        href = card.get("href", "") if isinstance(card, Tag) else ""

        # 判断类型
        is_skill = "/skill/" in href
        is_mcp = "/server/" in href

        tags: list[str] = []
        tag_els = card.select(".tag, [class*='tag'], .badge, [class*='badge']")
        for tag_el in tag_els:
            tag_text = tag_el.get_text(strip=True)
            if tag_text:
                tags.append(tag_text)

        result: dict[str, Any] = {
            "id": href.split("/")[-1] if href else "",
            "name": name_el.get_text(strip=True),
            "description": desc_el.get_text(strip=True) if desc_el else "",
            "plugin_type": "mcp_server" if is_mcp else ("skill" if is_skill else "mcp_server"),
            "source": "mcp_so",
            "source_url": f"https://mcp.so{href}" if href else "",
            "tags": tags,
            "trust_level": "community",
        }

        # 尝试提取 stars 数
        stars_el = card.select_one("[class*='star'], [class*='rating'], .stars")
        if stars_el:
            try:
                stars_text = stars_el.get_text(strip=True)
                result["stars"] = _parse_stars(stars_text)
            except (ValueError, TypeError):
                pass

        results.append(result)

    return results


def parse_mcp_aibase_html(html: str) -> list[dict[str, Any]]:
    """
    解析 mcp.aibase.cn 搜索页 HTML。

    mcp.aibase.cn 是纯 MCP Server 目录站，所有结果均为 mcp_server 类型。

    Args:
        html: 搜索页的 HTML 文本

    Returns:
        搜索结果字典列表
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []

    # mcp.aibase.cn 的服务器卡片
    cards = soup.select("a[href*='/server/'], .server-item, [class*='card'], [class*='item']")

    for card in cards:
        from bs4 import Tag
        if not isinstance(card, Tag):
            continue

        name_el = card.select_one("h3, h2, h4, .name, [class*='title']")
        desc_el = card.select_one("p, .description, [class*='desc'], [class*='summary']")

        if not name_el:
            continue

        href = card.get("href", "")
        name = name_el.get_text(strip=True)
        if not name:
            continue

        tags: list[str] = []
        tag_els = card.select(".tag, [class*='tag'], .badge, [class*='badge']")
        for tag_el in tag_els:
            tag_text = tag_el.get_text(strip=True)
            if tag_text:
                tags.append(tag_text)

        result: dict[str, Any] = {
            "id": href.split("/")[-1] if href else name.lower().replace(" ", "-"),
            "name": name,
            "description": desc_el.get_text(strip=True) if desc_el else "",
            "plugin_type": "mcp_server",
            "source": "mcp_aibase",
            "source_url": (
                f"https://mcp.aibase.cn{href}"
                if href and not href.startswith("http")
                else href
            ),
            "tags": tags,
            "trust_level": "community",
        }

        stars_el = card.select_one("[class*='star'], [class*='rating'], [class*='score']")
        if stars_el:
            with contextlib.suppress(ValueError, TypeError):
                result["stars"] = _parse_stars(stars_el.get_text(strip=True))

        results.append(result)

    return results


def parse_mcpmarket_html(html: str) -> list[dict[str, Any]]:
    """
    解析 mcpmarket.cn 搜索页 HTML。

    mcpmarket.cn 是中文 MCP 市场，所有结果均为 mcp_server 类型。

    Args:
        html: 搜索页的 HTML 文本

    Returns:
        搜索结果字典列表
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []

    cards = soup.select(".server-card, .market-item, [class*='card'], [class*='item'], tr")

    for card in cards:
        from bs4 import Tag
        if not isinstance(card, Tag):
            continue

        name_el = card.select_one("h3, h2, h4, .name, [class*='title'], a")
        desc_el = card.select_one("p, .description, [class*='desc'], td:nth-child(2)")

        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) > 100:
            continue

        href = ""
        if isinstance(name_el, Tag):
            href = name_el.get("href", "")

        tags: list[str] = []
        tag_els = card.select(".tag, [class*='tag'], .badge, [class*='badge']")
        for tag_el in tag_els:
            tag_text = tag_el.get_text(strip=True)
            if tag_text:
                tags.append(tag_text)

        result: dict[str, Any] = {
            "id": href.split("/")[-1] if href else name.lower().replace(" ", "-"),
            "name": name,
            "description": desc_el.get_text(strip=True) if desc_el else "",
            "plugin_type": "mcp_server",
            "source": "mcpmarket_cn",
            "source_url": (
                f"https://mcpmarket.cn{href}"
                if href and not href.startswith("http")
                else ""
            ),
            "tags": tags,
            "trust_level": "community",
        }

        results.append(result)

    return results


def _parse_stars(text: str) -> int:
    """
    解析星级/收藏数字符串。

    支持格式: "90.7K", "108.3K", "128", "4.5分", "5分"

    Args:
        text: 原始数字字符串

    Returns:
        解析后的整数
    """
    text = text.strip().replace(",", "").replace(" ", "")
    # 去掉 "分" 后缀
    text = text.replace("分", "")

    if text.endswith("K") or text.endswith("k"):
        return int(float(text[:-1]) * 1000)
    if text.endswith("M") or text.endswith("m"):
        return int(float(text[:-1]) * 1_000_000)
    try:
        return int(float(text))
    except (ValueError, TypeError):
        return 0
