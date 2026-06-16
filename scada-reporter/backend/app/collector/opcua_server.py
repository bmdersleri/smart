import asyncio
import logging

from asyncua import Server, ua
from sqlalchemy import select

from app.collector.cache import latest_cache
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.tag import Tag

logger = logging.getLogger(__name__)


class OpcUaServer:
    def __init__(self) -> None:
        self.server = Server()
        self._task: asyncio.Task | None = None
        self._idx: int | None = None
        self._tag_nodes: dict[int, ua.Node] = {}
        self._device_folders: dict[str, ua.Node] = {}

    async def start(self) -> None:
        await self.server.init()
        self.server.set_endpoint(f"opc.tcp://0.0.0.0:{settings.OPCUA_SERVER_PORT}")
        self.server.set_server_name("SCADA Reporter OPC UA Server")
        self._idx = await self.server.register_namespace(settings.OPCUA_SERVER_URI)

        root = self.server.nodes.objects
        tags_folder = await root.add_object(self._idx, "Tags")

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tag).where(Tag.is_active))
            tags = result.scalars().all()

            for n, tag in enumerate(tags):
                device_folder = await self._ensure_device(tags_folder, tag.device)
                var = await device_folder.add_variable(
                    self._idx,
                    tag.name,
                    0.0,
                )
                await var.set_writable(False)
                if tag.unit:
                    await var.set_attr(
                        ua.AttributeIds.DISPLAY_NAME,
                        ua.LocalizedText(f"{tag.name} [{tag.unit}]"),
                    )
                self._tag_nodes[tag.id] = var
                # Çok sayıda tag'de event loop'u aç tut (HTTP responsive kalsın)
                if n % 100 == 0:
                    await asyncio.sleep(0)

        logger.info(
            "OPC UA server baslatildi: opc.tcp://0.0.0.0:%d | %d tag yayinda",
            settings.OPCUA_SERVER_PORT,
            len(self._tag_nodes),
        )
        self._task = asyncio.create_task(self._update_loop())

    async def _ensure_device(
        self,
        parent: ua.Node,
        device: str,
    ) -> ua.Node:
        # Cihaz klasörünü cache'le (get_children() O(n^2) taramasını önle)
        key = device or "—"
        node = self._device_folders.get(key)
        if node is None:
            node = await parent.add_object(self._idx, key)
            self._device_folders[key] = node
        return node

    async def _apply_latest(self) -> int:
        """Cache'teki son değerleri OPC UA node'larına yaz. Yazılan sayıyı döner."""
        updated = 0
        for tag_id, node in self._tag_nodes.items():
            cr = latest_cache.get(tag_id)
            if cr is not None and cr.value is not None:
                await node.write_value(ua.Variant(float(cr.value), ua.VariantType.Double))
                updated += 1
        return updated

    async def _update_loop(self) -> None:
        while True:
            try:
                await self._apply_latest()
            except Exception as e:
                logger.error("OPC UA guncelleme hatasi: %s", e)
            await asyncio.sleep(settings.OPCUA_SERVER_UPDATE_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        await self.server.stop()
        logger.info("OPC UA server durduruldu")


opcua_server = OpcUaServer()
