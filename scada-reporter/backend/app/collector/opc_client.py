import asyncio
import logging
from datetime import datetime
from asyncua import Client, Node
from app.core.config import settings

logger = logging.getLogger(__name__)


class OpcUaCollector:
    def __init__(self):
        self.client: Client | None = None
        self.subscriptions: dict = {}
        self._running = False

    async def connect(self):
        self.client = Client(url=settings.OPC_UA_URL, timeout=10)
        if settings.OPC_UA_USERNAME:
            self.client.set_user(settings.OPC_UA_USERNAME)
            self.client.set_password(settings.OPC_UA_PASSWORD)
        try:
            await self.client.connect()
            self._running = True
            logger.info("OPC UA baglantisi kuruldu: %s", settings.OPC_UA_URL)
        except Exception:
            self.client = None
            raise

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            logger.info("OPC UA baglantisi kapatildi")

    async def browse_tags(self, node_id: str = "ns=2;s=.") -> list[dict]:
        """KEPServerEX tag agacini tarar."""
        if not self.client:
            raise RuntimeError("OPC UA baglantisi yok")
        node = self.client.get_node(node_id)
        return await self._browse_recursive(node, depth=0, max_depth=4)

    async def _browse_recursive(self, node: Node, depth: int, max_depth: int) -> list[dict]:
        if depth > max_depth:
            return []
        results = []
        try:
            children = await node.get_children()
            for child in children:
                try:
                    name = (await child.read_browse_name()).Name
                    node_class = await child.read_node_class()
                    node_id_str = child.nodeid.to_string()

                    if node_class.name == "Variable":
                        results.append({
                            "node_id": node_id_str,
                            "name": name,
                            "depth": depth,
                        })
                    else:
                        results.extend(
                            await self._browse_recursive(child, depth + 1, max_depth)
                        )
                except Exception:
                    continue
        except Exception as e:
            logger.warning("Browse hatasi: %s", e)
        return results

    async def read_tag(self, node_id: str) -> tuple[float | None, int, datetime]:
        """Tek tag okur. (value, quality, timestamp) döner."""
        node = self.client.get_node(node_id)
        dv = await node.read_data_value()
        value = float(dv.Value.Value) if dv.Value.Value is not None else None
        quality = dv.StatusCode.value
        ts = dv.SourceTimestamp or datetime.utcnow()
        return value, quality, ts

    async def read_tags_bulk(self, node_ids: list[str]) -> list[tuple]:
        """Toplu tag okuma."""
        nodes = [self.client.get_node(nid) for nid in node_ids]
        data_values = await self.client.read_values(nodes)
        result = []
        for nid, dv in zip(node_ids, data_values):
            try:
                value = float(dv) if dv is not None else None
                result.append((nid, value, 192, datetime.utcnow()))
            except (TypeError, ValueError):
                result.append((nid, None, 0, datetime.utcnow()))
        return result


collector = OpcUaCollector()
