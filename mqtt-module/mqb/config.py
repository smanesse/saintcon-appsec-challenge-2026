import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    host: str
    port: int
    admin_host: str
    admin_port: int
    require_pass: Optional[str]
    retain_dir: str
    keepalive_grace: float
    flag: str
    flag_topic: str
    flag_file: str

    @classmethod
    def from_env(cls) -> "Config":
        port = int(os.environ.get("SERVER_PORT") or os.environ.get("MQB_PORT", "1883"))
        require_pass = os.environ.get("MQB_REQUIREPASS") or None
        return cls(
            host=os.environ.get("MQB_HOST", "0.0.0.0"),
            port=port,
            admin_host=os.environ.get("MQB_ADMIN_HOST", "0.0.0.0"),
            admin_port=int(os.environ.get("MQB_ADMIN_PORT", "8081")),
            require_pass=require_pass,
            retain_dir=os.environ.get("MQB_RETAIN_DIR", "./retained"),
            keepalive_grace=float(os.environ.get("MQB_KEEPALIVE_GRACE", "1.5")),
            flag=os.environ.get("MQB_FLAG") or "FLAG{local-dev-default}",
            flag_topic=os.environ.get("MQB_FLAG_TOPIC", "fleet/control/flag"),
            flag_file=os.environ.get("MQB_FLAG_FILE", "./secret/flag.txt"),
        )
