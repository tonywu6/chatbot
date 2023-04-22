import inspect
import json
import os
from functools import cache
from pathlib import Path
from typing import Callable, TypeVar

import toml
import yaml
from loguru import logger
from pydantic import BaseSettings, Extra, SecretStr, ValidationError
from pydantic.env_settings import SettingsSourceCallable

profile: str | None = None


def set_profile(name: str | None):
    global profile
    profile = name


def path_with_profile(path: Path) -> Path:
    if profile is None:
        return path
    return path.with_name(f"{path.stem}@{profile}{path.suffix}")


def toml_config_loader(path: Path) -> Callable[[BaseSettings], dict]:
    @cache
    def cached_read(path: Path):
        return toml.loads(path.read_text())

    def loader(settings: BaseSettings) -> dict:
        actual_path = path_with_profile(path)
        if not actual_path.exists():
            logger.warning(f"Config file {actual_path} does not exist")
            return {}
        return cached_read(actual_path)

    return loader


def yaml_config_loader(path: Path) -> Callable[[BaseSettings], dict]:
    @cache
    def cached_read(path: Path):
        return yaml.safe_load(path.read_text()) or {}

    def loader(settings: BaseSettings) -> dict:
        actual_path = path_with_profile(path)
        if not actual_path.exists():
            logger.warning(f"Config file {actual_path} does not exist")
            return {}
        return cached_read(actual_path)

    return loader


class _AugmentedConfig(BaseSettings.Config):
    config_path = Path

    @classmethod
    def exists(cls) -> bool:
        ...

    @classmethod
    def write(cls, obj: BaseSettings):
        ...


def use_settings_file(path: str | Path, **extra_config) -> type[_AugmentedConfig]:
    path = Path(path)
    if path.suffix == ".toml":
        loader = toml_config_loader(path)
        writer = toml.dumps
    elif path.suffix in [".yaml", ".yml", ".json"]:
        loader = yaml_config_loader(path)
        writer = yaml.dump
    else:
        raise NotImplementedError(f"Unsupported config file of suffix {path.suffix}")

    class Config:
        allow_mutation = False
        extra = Extra.forbid
        config_path = path
        json_encoders = {SecretStr: lambda v: v.get_secret_value()}

        @classmethod
        def customise_sources(
            cls,
            init_settings: SettingsSourceCallable,
            env_settings: SettingsSourceCallable,
            file_secret_settings: SettingsSourceCallable,
        ):
            return (init_settings, env_settings, file_secret_settings, loader)

        @classmethod
        def exists(cls):
            return path.exists()

        @classmethod
        def write(cls, obj: BaseSettings):
            os.makedirs(path.parent, exist_ok=True)
            with open(path, "w") as f:
                f.write(writer(json.loads(obj.json())))

    for k, v in extra_config.items():
        setattr(Config, k, v)

    return Config


T = TypeVar("T", bound=BaseSettings)


def load_settings(settings_cls: type[T]) -> T:
    try:
        return settings_cls()
    except ValidationError as e:
        filename = inspect.getsourcefile(settings_cls)
        lines, line_no = inspect.getsourcelines(settings_cls)
        expected_path = path_with_profile(settings_cls.Config.config_path)
        logger.error(
            f"\nError loading settings: {settings_cls.__name__}"
            "\n------------"
            f"\nExpected location: {expected_path}"
            " (or provide via environment variables)"
            f"\nSettings defined at {filename}:{line_no}"
            "\n------------"
            f"\n{{error}}",
            error=str(e),
        )
        raise SystemExit(2)
