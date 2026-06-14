import logging
from snap7 import Client
from app.core.config import settings

logger = logging.getLogger(__name__)


class S7Client:
    def __init__(self) -> None:
        self.client: Client | None = None

    async def connect(self) -> None:
        try:
            c = Client()
            c.connect(settings.S7_HOST, settings.S7_RACK, settings.S7_SLOT)
            info = c.get_cpu_info()
            self.client = c
            logger.info(
                "S7-1500 baglandi: %s | %s %s %s",
                settings.S7_HOST,
                info.ModuleTypeName.decode(),
                info.SerialNumber.decode(),
                info.ASName.decode(),
            )
        except Exception as e:
            logger.warning("S7-1500 baglanti hatasi: %s", e)
            self.client = None

    async def disconnect(self) -> None:
        if self.client:
            self.client.disconnect()
            self.client.destroy()
            self.client = None
            logger.info("S7-1500 baglantisi kesildi")

    def is_connected(self) -> bool:
        return self.client is not None and self.client.get_connected()


s7_client = S7Client()
