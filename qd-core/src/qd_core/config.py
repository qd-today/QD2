"""QD Core configuration settings."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

# Default config directory: ~/.qd2
DEFAULT_CONFIG_DIR = Path.home() / ".qd2"


class QDBaseSettings(BaseSettings):
    """Base settings class for QD modules."""

    model_config = {
        "env_prefix": "QD_",
        "env_nested_delimiter": "__",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


class QDCoreSettings(QDBaseSettings):
    """Core framework settings."""

    config_dir: Path = Field(
        default_factory=lambda: DEFAULT_CONFIG_DIR,
        description="QD2 configuration directory",
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Log level")

    # i18n
    locale: str = Field(default="zh_CN", description="Locale for i18n")

    # HTTP client defaults
    request_timeout: int = Field(default=30, description="Default HTTP request timeout in seconds")
    max_retries: int = Field(default=3, description="Default max retries for HTTP requests")

    def ensure_config_dir(self) -> None:
        """Create config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)


def export_settings_to_json(settings: BaseSettings, output_path: Optional[Path] = None) -> None:
    """Export settings to a JSON file for debugging."""
    import json

    if output_path is None:
        output_path = Path("settings.json")

    data = settings.model_dump()
    output_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
