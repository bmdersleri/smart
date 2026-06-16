"""Çoklu-PLC S7 veri toplayıcı.

WinCC export adres sözdizimini (DB301,DD7890 / DB310,DBW90 / Q254.1) çözer,
PLC başına bir snap7 bağlantısı tutar (thread-safe lock ile) ve erişilemeyen
PLC'lerde simülasyon modunda (value=None, quality=0) sorunsuz devam eder.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

import snap7
from snap7.type import Areas
from snap7.util import get_bool, get_byte, get_dint, get_int, get_real, get_word

from app.core.config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=settings.S7_MAX_WORKERS, thread_name_prefix="snap7")

GOOD = 192  # OPC kalite: iyi
BAD = 0

# Blok okuma: ardışık DB adreslerini tek db_read'e topla (PDU round-trip azalt)
MAX_BLOCK_BYTES = 222  # en küçük S7 PDU (240) için güvenli tek-okuma payload'u
BLOCK_GAP_TOLERANCE = 32  # bu kadar boşluğa kadar iki spec aynı bloğa birleşir

# Operand mnemonik -> okunacak byte sayısı
_OPERAND_SIZES = {
    "DD": 4,
    "DBD": 4,  # DB double word
    "DW": 2,
    "DBW": 2,  # DB word
    "DBB": 1,  # DB byte
    "DBX": 1,  # DB bit
    "D": 1,  # DB bit (WinCC kısa form: DBxxx,D<byte>.<bit>)
    # legacy (eski seed formatı, geri uyum)
    "REAL": 4,
    "DINT": 4,
    "INT": 2,
    "WORD": 2,
    "BOOL": 1,
}

# WinCC veri tipi -> (decoder, byte sayısı)
_DTYPE_MAP = {
    "FLOAT32": ("REAL", 4),
    "FLOAT64": ("REAL", 4),
    "FLOATING-POINT NUMBER 32-BIT IEEE 754": ("REAL", 4),
    "FLOATING-POINT NUMBER 64-BIT IEEE 754": ("REAL", 4),
    "REAL": ("REAL", 4),
    "UINT16": ("WORD", 2),
    "UNSIGNED 16-BIT VALUE": ("WORD", 2),
    "WORD": ("WORD", 2),
    "INT16": ("INT", 2),
    "SIGNED 16-BIT VALUE": ("INT", 2),
    "INT": ("INT", 2),
    "INT32": ("DINT", 4),
    "DINT": ("DINT", 4),
    "BINARY": ("BOOL", 1),
    "BINARY TAG": ("BOOL", 1),
    "BOOL": ("BOOL", 1),
    "BYTE": ("BYTE", 1),
    "SINT": ("BYTE", 1),
    "USINT": ("BYTE", 1),
    "SIGNED 8-BIT VALUE": ("BYTE", 1),
    "UNSIGNED 8-BIT VALUE": ("BYTE", 1),
}

_DB_RE = re.compile(r"^DB(\d+),([A-Z]+)(\d+)(?:\.(\d+))?$")
_AREA_RE = re.compile(r"^([QIEM])(\d+)\.(\d+)$")


@dataclass(frozen=True)
class ReadSpec:
    area: str  # "DB" | "PA" (Q çıkış) | "PE" (I/E giriş) | "MK"
    db_number: int  # DB dışı alanlarda 0
    byte_offset: int
    bit: int  # bit erişimi değilse 0
    size: int  # okunacak byte sayısı
    decoder: str  # "REAL" | "WORD" | "INT" | "DINT" | "BOOL"


def _decoder_for(operand: str, data_type: str | None) -> tuple[str, int]:
    """Decode tipini öncelikle WinCC veri tipinden, yoksa operand'dan türet."""
    if data_type:
        key = data_type.strip().upper()
        if key in _DTYPE_MAP:
            return _DTYPE_MAP[key]
    # data_type yok/bilinmiyor -> operand'a düş
    if operand in ("DD", "DBD"):
        return "REAL", 4
    if operand in ("DW", "DBW", "WORD"):
        return "WORD", 2
    if operand == "DBB":
        return "BYTE", 1
    if operand in ("DBX", "BOOL", "D"):
        return "BOOL", 1
    if operand in ("REAL", "INT", "DINT"):
        return operand, _OPERAND_SIZES[operand]
    return "REAL", 4


def parse_address(address: str, data_type: str | None = None) -> ReadSpec:
    """WinCC operand adresini çözer. Bilinmeyen formatta ValueError."""
    addr = address.strip().upper()

    m = _DB_RE.match(addr)
    if m:
        db_num = int(m.group(1))
        operand = m.group(2)
        byte_off = int(m.group(3))
        bit = int(m.group(4)) if m.group(4) is not None else 0
        if operand not in _OPERAND_SIZES:
            raise ValueError(f"Bilinmeyen DB operandı: {operand} ({address})")
        decoder, size = _decoder_for(operand, data_type)
        return ReadSpec("DB", db_num, byte_off, bit, size, decoder)

    m = _AREA_RE.match(addr)
    if m:
        prefix, byte_off, bit = m.group(1), int(m.group(2)), int(m.group(3))
        area = {"Q": "PA", "I": "PE", "E": "PE", "M": "MK"}[prefix]
        return ReadSpec(area, 0, byte_off, bit, 1, "BOOL")

    raise ValueError(f"Cozumlenemeyen S7 adresi: {address}")


def _decode(spec: ReadSpec, data: bytearray) -> float | None:
    if spec.decoder == "REAL":
        return float(get_real(data, 0))
    if spec.decoder == "INT":
        return float(get_int(data, 0))
    if spec.decoder == "DINT":
        return float(get_dint(data, 0))
    if spec.decoder == "WORD":
        return float(get_word(data, 0))
    if spec.decoder == "BYTE":
        return float(get_byte(data, 0))
    if spec.decoder == "BOOL":
        return float(get_bool(data, 0, spec.bit))
    return None


@dataclass(frozen=True)
class DbBlock:
    """Tek db_read ile okunacak ardışık byte aralığı + içindeki tag'ler."""

    db_number: int
    start: int
    size: int
    members: tuple[tuple[int, ReadSpec], ...]  # (opak anahtar, spec)


def plan_db_blocks(items: list[tuple[int, ReadSpec]]) -> list[DbBlock]:
    """Aynı DB içindeki ardışık spec'leri tek bloğa toplar.

    items: (key, ReadSpec); key sonuçları geri eşlemek için opaktır (ör. orijinal
    indeks). Sadece area == 'DB' spec'ler verilmelidir.
    """
    by_db: dict[int, list[tuple[int, ReadSpec]]] = defaultdict(list)
    for key, sp in items:
        by_db[sp.db_number].append((key, sp))

    blocks: list[DbBlock] = []
    for db_number, group in by_db.items():
        group.sort(key=lambda ks: ks[1].byte_offset)
        start: int | None = None
        end = 0
        members: list[tuple[int, ReadSpec]] = []
        for key, sp in group:
            sp_end = sp.byte_offset + sp.size
            if (
                start is not None
                and sp.byte_offset - end <= BLOCK_GAP_TOLERANCE
                and sp_end - start <= MAX_BLOCK_BYTES
            ):
                end = max(end, sp_end)
                members.append((key, sp))
            else:
                if start is not None:
                    blocks.append(DbBlock(db_number, start, end - start, tuple(members)))
                start, end = sp.byte_offset, sp_end
                members = [(key, sp)]
        if start is not None:
            blocks.append(DbBlock(db_number, start, end - start, tuple(members)))
    return blocks


_AREA_ENUM = {"DB": Areas.DB, "PA": Areas.PA, "PE": Areas.PE, "MK": Areas.MK}


class PLCConnection:
    """Tek bir PLC'ye snap7 bağlantısı. Bloklayan çağrılar lock ile serileştirilir."""

    RECONNECT_BACKOFF = 10.0  # saniye

    def __init__(self, ip: str, rack: int = 0, slot: int = 1, name: str = ""):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.name = name
        self._client: snap7.client.Client | None = None
        self._lock = threading.Lock()
        self._connected = False
        self._last_attempt = 0.0

    @property
    def connected(self) -> bool:
        return self._connected

    def _ensure_connected_sync(self) -> bool:
        if self._connected and self._client is not None:
            return True
        now = time.monotonic()
        if now - self._last_attempt < self.RECONNECT_BACKOFF:
            return False
        self._last_attempt = now
        try:
            client = snap7.client.Client()
            try:
                # connect/recv zaman aşımını kısalt (thread asılı kalmasın), ms
                from snap7.type import Parameter

                client.set_param(Parameter.PingTimeout, 750)
                client.set_param(Parameter.SendTimeout, 1000)
                client.set_param(Parameter.RecvTimeout, 1500)
            except Exception:
                pass
            client.connect(self.ip, self.rack, self.slot)
            self._client = client
            self._connected = True
            logger.info("PLC baglandi: %s (%s)", self.ip, self.name or "?")
            return True
        except Exception as e:
            self._connected = False
            self._client = None
            logger.warning("PLC baglanamadi %s (%s): %s", self.ip, self.name, e)
            return False

    def read_batch_sync(self, specs: list[ReadSpec]) -> list[tuple[float | None, int]]:
        """specs sırasına göre (value, quality) listesi döner."""
        with self._lock:
            if not self._ensure_connected_sync():
                return [(None, BAD)] * len(specs)
            results: list[tuple[float | None, int]] = []
            client = self._client
            assert client is not None
            for i, spec in enumerate(specs):
                try:
                    if spec.area == "DB":
                        data = client.db_read(spec.db_number, spec.byte_offset, spec.size)
                    else:
                        data = client.read_area(
                            _AREA_ENUM[spec.area], 0, spec.byte_offset, spec.size
                        )
                    results.append((_decode(spec, data), GOOD))
                except Exception as e:
                    # Bağlantı hâlâ ayakta mı? Ayakta ise bu tek tag'in veri hatası
                    # (adres yok / geçersiz) -> sadece bu tag'i BAD yap, devam et.
                    still_up = False
                    try:
                        still_up = bool(client.get_connected())
                    except Exception:
                        still_up = False
                    if still_up:
                        logger.warning("Tag okuma hatasi %s @%s: %s", self.ip, spec, e)
                        results.append((None, BAD))
                        continue
                    # gerçek bağlantı kopması -> kalan tümünü BAD yap, yeniden bağlan
                    logger.warning("PLC baglanti koptu %s @%s: %s", self.ip, spec, e)
                    self._connected = False
                    self._client = None
                    results.extend([(None, BAD)] * (len(specs) - i))
                    break
            return results

    def disconnect_sync(self) -> None:
        with self._lock:
            if self._client is not None:
                with contextlib.suppress(Exception):
                    self._client.disconnect()
            self._client = None
            self._connected = False


class PLCManager:
    """(ip, rack, slot) -> PLCConnection kayıt defteri. Lazy bağlanır."""

    def __init__(self) -> None:
        self._conns: dict[tuple[str, int, int], PLCConnection] = {}
        self._registry_lock = threading.Lock()

    def get(self, ip: str, rack: int = 0, slot: int = 1, name: str = "") -> PLCConnection:
        key = (ip, rack, slot)
        with self._registry_lock:
            conn = self._conns.get(key)
            if conn is None:
                conn = PLCConnection(ip, rack, slot, name)
                self._conns[key] = conn
            return conn

    async def read_one(
        self, ip: str, rack: int, slot: int, spec: ReadSpec, name: str = ""
    ) -> tuple[float | None, int]:
        conn = self.get(ip, rack, slot, name)
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(_executor, conn.read_batch_sync, [spec])
        return results[0]

    async def read_plc_batch(
        self, ip: str, rack: int, slot: int, specs: list[ReadSpec], name: str = ""
    ) -> list[tuple[float | None, int]]:
        conn = self.get(ip, rack, slot, name)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, conn.read_batch_sync, specs)

    def status(self) -> dict[str, bool]:
        with self._registry_lock:
            return {c.ip: c.connected for c in self._conns.values()}

    async def disconnect_all(self) -> None:
        loop = asyncio.get_event_loop()
        with self._registry_lock:
            conns = list(self._conns.values())
        for conn in conns:
            await loop.run_in_executor(_executor, conn.disconnect_sync)


plc_manager = PLCManager()


async def read_tag_now(
    address: str | None,
    data_type: str | None,
    ip: str | None,
    rack: int = 0,
    slot: int = 1,
    name: str = "",
    timeout: float | None = None,
) -> tuple[float | None, int, datetime]:
    """Tek bir tag'i hemen oku (tag ekleme akışı için). Zaman aşımı/hata -> (None, 0)."""
    ts = datetime.now(UTC)
    if not address or not ip:
        return None, BAD, ts
    try:
        spec = parse_address(address, data_type)
    except ValueError as e:
        logger.warning("Adres cozulemedi %s: %s", address, e)
        return None, BAD, ts
    try:
        value, quality = await asyncio.wait_for(
            plc_manager.read_one(ip, rack, slot, spec, name),
            timeout=timeout if timeout is not None else settings.S7_READ_TIMEOUT,
        )
        return value, quality, datetime.now(UTC)
    except TimeoutError:
        logger.warning("Tag okuma zaman asimi %s @%s", address, ip)
        return None, BAD, datetime.now(UTC)
    except Exception as e:
        logger.warning("Tag okuma hatasi %s @%s: %s", address, ip, e)
        return None, BAD, datetime.now(UTC)
