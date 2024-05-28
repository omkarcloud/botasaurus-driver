from datetime import datetime
import json
import os
import random as random_module
from .driver_utils import relative_path

datetime_format = '%Y-%m-%d %H:%M:%S'

from typing import Any, overload

def str_to_datetime(when):
    return datetime.fromisoformat(when)

def datetime_to_str(when):
    return when.isoformat()

class JSONStorageBackend():

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

    def set_item(self, key: str, value: Any) -> None:
        if "created_at" not in value:
            value["created_at"] = datetime_to_str(datetime.now())

        value["updated_at"] = datetime_to_str(datetime.now())
         
        self.json_data[key] = {'profile_id': key, **value}
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


    
class Profile(dict):

    def __init__(self, profile:str) -> None:
        self.refresh_profiles()
        self.profile = profile
        super().__init__({ 'profile_id': self.profile, **self.json_data.get(profile, {})})

    def refresh_profiles(self):
        self.json_path = relative_path("profiles.json", 0)
        self.json_data = {}

        if not os.path.isfile(self.json_path):
            with open(self.json_path, "w") as json_file:
                json.dump(self.json_data, json_file, indent=4)

        with open(self.json_path, "r") as json_file:
            self.json_data = json.load(json_file)

    def commit_to_disk(self):
        self.json_data[self.profile] = { 'profile_id': self.profile, **self}
        with open(self.json_path, "w") as json_file:
            json.dump(self.json_data, json_file, indent=4)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)

        if "created_at" not in self:
            super().__setitem__("created_at", datetime_to_str(datetime.now()))

        super().__setitem__("updated_at", datetime_to_str(datetime.now()))
        self.refresh_profiles()
        self.commit_to_disk()

    def __delitem__(self, key):
        super().__delitem__(key)
        self.refresh_profiles()
        self.commit_to_disk()

    @overload
    def pop(self, key: str, default: Any): ...

    def pop(self, key, *args):
        result =  super().pop(key, *args)
        self.refresh_profiles()
        self.commit_to_disk()
        return result


class Profiles:
    storage_backend_instance = JSONStorageBackend()

    @staticmethod
    def get_profile(profile):
        Profiles.storage_backend_instance.refresh()
        return Profiles.storage_backend_instance.get_item(profile)

    @staticmethod
    def get_profiles(random=False):
        Profiles.storage_backend_instance.refresh()
        data = list(Profiles.storage_backend_instance.items().values())

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

    @staticmethod
    def set_profile(profile, data):
        Profiles.storage_backend_instance.refresh()
        Profiles.storage_backend_instance.set_item(profile, data)

    @staticmethod
    def delete_profile(profile):
        Profiles.storage_backend_instance.refresh()
        Profiles.storage_backend_instance.remove_item(profile)