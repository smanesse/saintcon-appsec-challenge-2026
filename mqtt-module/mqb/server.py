from __future__ import annotations

import asyncio
import logging
import sys

from .admin import start_admin_server
from .broker import Broker
from .config import Config


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config.from_env()
    broker = Broker(cfg)
    broker.seed_startup_state()

    start_admin_server(broker, cfg)
    logging.info("mqb admin HTTP listening on %s:%d", cfg.admin_host, cfg.admin_port)

    server = await asyncio.start_server(broker.handle_client, cfg.host, cfg.port)
    logging.info(
        "mqb MQTT 3.1.1 broker listening on %s:%d (auth %s)",
        cfg.host, cfg.port, "REQUIRED" if cfg.require_pass else "DISABLED (MQB_REQUIREPASS unset)",
    )
    async with server:
        await server.serve_forever()


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    run()
