from datetime import datetime
import json
import os
import random as random_module

from .driver_utils import relative_path

datetime_format = '%Y-%m-%d %H:%M:%S'

def str_to_datetime(when):
    return datetime.strptime(
        when, datetime_format)

def datetime_to_str(when):
    return when.strftime(datetime_format)

class ProfilePyStorageException(Exception):
    pass


class BasicStorageBackend:
    def raise_dummy_exception(self):
        raise ProfilePyStorageException("Called dummy backend!")

    def get_item(self, item: str, default: any = None) -> str:
        self.raise_dummy_exception()

    def set_item(self, item: str, value: any) -> None:
        self.raise_dummy_exception()

    def remove_item(self, item: str) -> None:
        self.raise_dummy_exception()

    def clear(self) -> None:
        self.raise_dummy_exception()


class JSONStorageBackend(BasicStorageBackend):
    def __init__(self) -> None:
        self.refresh()

    def refresh(self):
        self.json_path = relative_path("profiles.json", 0)
        self.json_data = {}

        if not os.path.isfile(self.json_path):
            self.commit_to_disk()

        with open(self.json_path, "r") as json_file:
            self.json_data = json.load(json_file)

    def commit_to_disk(self):
        with open(self.json_path, "w") as json_file:
            json.dump(self.json_data, json_file, indent=4)

    def get_item(self, key: str, default=None) -> str:
        if key in self.json_data:
            return self.json_data[key]
        return default

    def items(self):
        return self.json_data

    def set_item(self, key: str, value: any) -> None:
        if "created_at" not in value:
            value["created_at"] = datetime_to_str(datetime.now())

        value["updated_at"] = datetime_to_str(datetime.now())

        self.json_data[key] = value
        self.commit_to_disk()

    def remove_item(self, key: str) -> None:
        if key in self.json_data:
            self.json_data.pop(key)
            self.commit_to_disk()

    def clear(self) -> None:
        if os.path.isfile(self.json_path):
            os.remove(self.json_path)
        self.json_data = {}
        self.commit_to_disk()


class Profile:
    def __init__(self, profile) -> None:
        self.storage_backend_instance = JSONStorageBackend()
        self.profile = profile

    def _refresh(self) -> None:
        self.storage_backend_instance.refresh()

    def get_item(self, item: str, default=None) -> any:
        profile = self.storage_backend_instance.get_item(self.profile, {})

        if default is None:
            return profile.get(item)
        else:
            return profile.get(item, default)

    def set_item(self, item: str, value: any) -> None:
        profile = self.storage_backend_instance.get_item(self.profile, {})
        profile[item] = value

        self.storage_backend_instance.set_item(self.profile, profile)

    def remove_item(self, item: str) -> None:
        profile = self.storage_backend_instance.get_item(self.profile, {})
        del profile[item]

        self.storage_backend_instance.set_item(self.profile, profile)

    def clear(self):

        self.storage_backend_instance.remove_item(self.profile)

    def items(self):
        profile = self.storage_backend_instance.get_item(self.profile, {})
        return profile

    def get_profile(self, profile):
        if profile is None:
            raise Exception("No Profile Passed.")

        return self.storage_backend_instance.get_item(profile)

    def get_profiles(self, random=False):
        data = list(self.storage_backend_instance.items().values())

        if len(data) == 0:
            return data

        if data[0].get("created_at") is None:
            if random:
                random_module.shuffle(data)
            return data

        if random:
            random_module.shuffle(data)
        else:
            data = sorted(data, key=lambda x: str_to_datetime(x["created_at"]))

        return data
