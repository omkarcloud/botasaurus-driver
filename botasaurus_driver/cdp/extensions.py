# DO NOT EDIT THIS FILE!
#
# This file is generated from the CDP specification. If you need to make
# changes, edit the generator and regenerate all of the modules.
#
# CDP domain: Extensions (experimental)

from __future__ import annotations

import enum
import typing
from dataclasses import dataclass

from .util import T_JSON_DICT, event_class


class StorageArea(enum.Enum):
    """
    Storage areas.
    """

    SESSION = "session"
    LOCAL = "local"
    SYNC = "sync"
    MANAGED = "managed"

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, json: str) -> StorageArea:
        return cls(json)


def load_unpacked(path: str) -> typing.Generator[T_JSON_DICT, T_JSON_DICT, str]:
    """
    Installs an unpacked extension from the filesystem similar to
    --load-extension CLI flags. Returns extension ID once the extension
    has been installed. Available if the client is connected using the
    --remote-debugging-pipe flag and the --enable-unsafe-extension-debugging
    flag is set.

    :param path: Absolute file path.
    :returns: Extension id.
    """
    params: T_JSON_DICT = dict()
    params["path"] = path
    cmd_dict: T_JSON_DICT = {
        "method": "Extensions.loadUnpacked",
        "params": params,
    }
    json = yield cmd_dict
    return str(json["id"])


def get_storage_items(
    id_: str, storage_area: StorageArea, keys: typing.Optional[typing.List[str]] = None
) -> typing.Generator[T_JSON_DICT, T_JSON_DICT, dict]:
    """
    Gets data from extension storage in the given ``storageArea``. If ``keys`` is
    specified, these are used to filter the result.

    :param id_: ID of extension.
    :param storage_area: StorageArea to retrieve data from.
    :param keys: *(Optional)* Keys to retrieve.
    :returns:
    """
    params: T_JSON_DICT = dict()
    params["id"] = id_
    params["storageArea"] = storage_area.to_json()
    if keys is not None:
        params["keys"] = [i for i in keys]
    cmd_dict: T_JSON_DICT = {
        "method": "Extensions.getStorageItems",
        "params": params,
    }
    json = yield cmd_dict
    return dict(json["data"])


def remove_storage_items(
    id_: str, storage_area: StorageArea, keys: typing.List[str]
) -> typing.Generator[T_JSON_DICT, T_JSON_DICT, None]:
    """
    Removes ``keys`` from extension storage in the given ``storageArea``.

    :param id_: ID of extension.
    :param storage_area: StorageArea to remove data from.
    :param keys: Keys to remove.
    """
    params: T_JSON_DICT = dict()
    params["id"] = id_
    params["storageArea"] = storage_area.to_json()
    params["keys"] = [i for i in keys]
    cmd_dict: T_JSON_DICT = {
        "method": "Extensions.removeStorageItems",
        "params": params,
    }
    json = yield cmd_dict


def clear_storage_items(
    id_: str, storage_area: StorageArea
) -> typing.Generator[T_JSON_DICT, T_JSON_DICT, None]:
    """
    Clears extension storage in the given ``storageArea``.

    :param id_: ID of extension.
    :param storage_area: StorageArea to remove data from.
    """
    params: T_JSON_DICT = dict()
    params["id"] = id_
    params["storageArea"] = storage_area.to_json()
    cmd_dict: T_JSON_DICT = {
        "method": "Extensions.clearStorageItems",
        "params": params,
    }
    json = yield cmd_dict


def set_storage_items(
    id_: str, storage_area: StorageArea, values: dict
) -> typing.Generator[T_JSON_DICT, T_JSON_DICT, None]:
    """
    Sets ``values`` in extension storage in the given ``storageArea``. The provided ``values``
    will be merged with existing values in the storage area.

    :param id_: ID of extension.
    :param storage_area: StorageArea to set data in.
    :param values: Values to set.
    """
    params: T_JSON_DICT = dict()
    params["id"] = id_
    params["storageArea"] = storage_area.to_json()
    params["values"] = values
    cmd_dict: T_JSON_DICT = {
        "method": "Extensions.setStorageItems",
        "params": params,
    }
    json = yield cmd_dict
