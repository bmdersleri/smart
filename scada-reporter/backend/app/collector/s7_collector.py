import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import snap7
from snap7.util import get_bool, get_dint, get_int, get_real, get_word

from app.core.config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="snap7")

_TYPE_SIZES = {"REAL": 4, "INT": 2, "DINT": 4, "WORD": 2, "BOOL": 1}


def _parse_address(address: str) -> tuple[int, str, int, int]:
    db_part, rest = address.upper().split(",", 1)
    db_num = int(db_part[2:])
    for t in _TYPE_SIZES:
        if rest.startswith(t):
            suffix = rest[len(t) :]
            if "." in suffix:
                byte_off, bit = suffix.split(".", 1)
                return db_num, t, int(byte_off), int(bit)
            return db_num, t, int(suffix), 0
    raise ValueError(f"Bilinmeyen S7 tipi: {rest}")


def _read_sync(client: snap7.client.Client, address: str) -> float | None:
    db_num, type_name, offset, bit = _parse_address(address)
    data = client.db_read(db_num, offset, _TYPE_SIZES[type_name])
    if type_name == "REAL":
        return float(get_real(data, 0))
    if type_name == "INT":
        return float(get_int(data, 0))
    if type_name == "DINT":
        return float(get_dint(data, 0))
    if type_name == "WORD":
        return float(get_word(data, 0))
    if type_name == "BOOL":
        return float(get_bool(data, 0, bit))
    return None


class S7Collector:
    def __init__(self):
        self.client: snap7.client.Client | None = None
        self._running = False

    async def connect(self):
        loop = asyncio.get_event_loop()
        client = snap7.client.Client()
        await loop.run_in_executor(
            _executor,
            lambda: client.connect(settings.S7_HOST, settings.S7_RACK, settings.S7_SLOT),
        )
        try:
            info = client.get_cpu_info()
            logger.info(
                "S7-1500 baglandi: %s | %s %s %s",
                settings.S7_HOST,
                info.ModuleTypeName.decode(),
                info.SerialNumber.decode(),
                info.ASName.decode(),
            )
        except Exception:
            logger.info(
                "S7 baglantisi kuruldu: %s rack=%d slot=%d",
                settings.S7_HOST,
                settings.S7_RACK,
                settings.S7_SLOT,
            )
        self.client = client
        self._running = True

    async def disconnect(self):
        if self.client:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_executor, self.client.disconnect)
            self.client = None
            self._running = False
            logger.info("S7 baglantisi kapatildi")

    async def browse_tags(self, node_id: str = "") -> list[dict]:
        return []

    async def read_tag(self, address: str) -> tuple[float | None, int, datetime]:
        if not self.client:
            return None, 0, datetime.now(UTC)
        loop = asyncio.get_event_loop()
        try:
            value = await loop.run_in_executor(_executor, _read_sync, self.client, address)
            return value, 192, datetime.now(UTC)
        except Exception as e:
            logger.warning("Tag okuma hatasi %s: %s", address, e)
            return None, 0, datetime.now(UTC)

    async def read_tags_bulk(self, addresses: list[str]) -> list[tuple]:
        results = []
        for addr in addresses:
            value, quality, ts = await self.read_tag(addr)
            results.append((addr, value, quality, ts))
        return results


collector = S7Collector()
