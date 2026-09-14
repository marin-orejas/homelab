import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DASHBOARD_", extra="ignore")

    jellyfin_url: str = "http://jellyfin:8096"
    jellyfin_api_key: str = ""
    jellyfin_timeout: float = 5.0

    service_specs: str = ""

    service_ttl_seconds: float = 30.0

    service_timeout: float = 5.0

    procfs_path: str = "/host/proc"

    hostname: str = ""

    disk_mounts: str = (
        "root=/host/root,"
        "wd1tb=/host/disks/wd1tb,"
        "toshiba2tb=/host/disks/toshiba2tb"
    )

    io_devices: str = ""

    net_interfaces: str = ""

    top_processes: int = 10

    snapshot_ttl_seconds: float = 2.0

    docker_api_url: str = ""

    smart_state_path: str = "/host/smart/latest.json"

    smart_stale_after_seconds: int = 26 * 3600

    history_enabled: bool = True

    history_db_path: str = "/data/history.db"

    history_interval_seconds: int = 30

    history_retention_days: int = 30

    cors_origins: str = ""

    access_mode: str = "off"

    access_team_domain: str = ""

    access_aud: str = ""

    docs_enabled: bool = False

    def parsed_disk_mounts(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for pair in self.disk_mounts.split(","):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            label, path = pair.split("=", 1)
            result[label.strip()] = path.strip()
        return result

    def parsed_io_devices(self) -> list[str]:
        return [d.strip() for d in self.io_devices.split(",") if d.strip()]

    def parsed_net_interfaces(self) -> list[str]:
        return [i.strip() for i in self.net_interfaces.split(",") if i.strip()]

    def parsed_service_specs(self) -> list[tuple[str, str, str]]:
        """Service specs as (name, kind, url) triples."""
        raw = self.service_specs.strip()
        if not raw:
            if not self.jellyfin_url:
                return []
            return [("jellyfin", "jellyfin", self.jellyfin_url)]

        specs: list[tuple[str, str, str]] = []
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":", 2)
            if len(parts) != 3:
                continue
            name, kind, url = (part.strip() for part in parts)
            if name and kind and url:
                specs.append((name, kind, url))
        return specs

    def service_api_key(self, name: str) -> str:
        """The key for one service, read straight from the environment."""
        if name == "jellyfin" and self.jellyfin_api_key:
            return self.jellyfin_api_key
        return os.environ.get(self.service_key_variable(name), "")

    def service_key_variable(self, name: str) -> str:
        """The environment variable a service's key is expected in."""
        if name == "jellyfin":
            return "DASHBOARD_JELLYFIN_API_KEY"
        return f"DASHBOARD_SERVICE_KEY_{name.upper()}"


settings = Settings()
