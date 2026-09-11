"""Async: async functions and async methods (v0.16.0 indexed)."""

import asyncio


async def fetch_page(url: str) -> str:
    await asyncio.sleep(0.01)
    return f"<html>{url}</html>"


async def fetch_many(urls: list[str]) -> list[str]:
    results = []
    for url in urls:
        page = await fetch_page(url)
        results.append(page)
    return results


class Downloader:
    def __init__(self, concurrency: int = 3) -> None:
        self.concurrency = concurrency

    async def download_all(self, urls: list[str]) -> int:
        pages = await fetch_many(urls)
        return len(pages)

    async def close(self) -> None:
        await asyncio.sleep(0)