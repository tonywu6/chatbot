import json
import os
from functools import cache
from pathlib import Path
from typing import Callable

import toml
import yaml
from loguru import logger
from pydantic import BaseSettings, Extra, SecretStr
from pydantic.env_settings import SettingsSourceCallable


def toml_config_loader(path: Path) -> Callable[[BaseSettings], dict]:
    @cache
    def cached_read(path: Path):
        return toml.loads(path.read_text())

    def loader(settings: BaseSettings) -> dict:
        if not path.exists():
            logger.warning(f"Config file {path} does not exist")
            return {}
        return cached_read(path)

    return loader


def yaml_config_loader(path: Path) -> Callable[[BaseSettings], dict]:
    @cache
    def cached_read(path: Path):
        return yaml.safe_load(path.read_text())

    def loader(settings: BaseSettings) -> dict:
        if not path.exists():
            logger.warning(f"Config file {path} does not exist")
            return {}
        return cached_read(path)

    return loader


class _AugmentedConfig:
    config_path = Path

    @classmethod
    def exists(cls) -> bool:
        ...

    @classmethod
    def write(cls, obj: BaseSettings):
        ...


_SettingsConfig = _AugmentedConfig | BaseSettings.Config


def use_settings_file(path: str | Path, **extra_config) -> _SettingsConfig:
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
