# quantbot/infrastructure/binance/binance_archive_downloader.py
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx

from quantbot.infrastructure.binance.binance_archive_url_builder import (
    BinanceArchiveUrlBuilder,
)


class BinanceArchiveDownloader:
    """把批次 zip 的位元組拿到手並確認完整：控併發、驗 checksum、快取到本機。

    只負責位元組。不解讀內容（那是 parser 的事），也不知道要抓哪幾個月
    （那是 candle source 的事）。httpx 的 client 由組裝根建立並注入，
    一個行程共用一個連線池。
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        url_builder: BinanceArchiveUrlBuilder,
        *,
        cache_directory: Path,
        concurrency: int = 8,
    ) -> None:
        self._client = client
        self._url_builder = url_builder
        self._cache_directory = cache_directory
        self._semaphore = asyncio.Semaphore(concurrency)

    async def download(self, archive_url: str) -> bytes | None:
        """下載一個 zip 並用官方 checksum 驗證。

        回傳 zip 的位元組；**檔案不存在（尚未上傳）時回傳 None**，因為當月的
        月檔本來就不存在、昨天的日檔可能還沒上傳完。把 404 當例外往上丟的話，
        程式每次跑到最新那幾天都會炸。

        本機已經有驗證過的檔案就直接讀，所以中斷後重跑不會重下。
        """
        cached = self._cache_directory / archive_url.rsplit("/", 1)[-1]
        if cached.exists():
            return cached.read_bytes()

        async with self._semaphore:
            expected = await self._read_checksum(archive_url)
            if expected is None:
                return None  # 連 checksum 都沒有，代表這個檔案還沒上傳
            payload = await self._read_bytes(archive_url)

        if payload is None:
            return None

        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise ValueError(
                f"checksum 不符：{archive_url}（預期 {expected}，實得 {actual}）"
            )

        self._write_verified(cached, payload)
        return payload

    async def _read_bytes(self, url: str) -> bytes | None:
        response = await self._client.get(url)
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        response.raise_for_status()
        return response.content

    async def _read_checksum(self, archive_url: str) -> str | None:
        """官方 .CHECKSUM 檔的格式是「<sha256>  <檔名>」。"""
        payload = await self._read_bytes(self._url_builder.checksum(archive_url))
        return None if payload is None else payload.decode().split()[0]

    def _write_verified(self, target: Path, payload: bytes) -> None:
        """先寫 .part 再改名，讓快取只有兩種狀態：完整可用，或不存在。"""
        self._cache_directory.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".part")
        temporary.write_bytes(payload)
        temporary.rename(target)
