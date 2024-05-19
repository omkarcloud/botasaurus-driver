class LocalStorage:
    def __init__(self, driver):
        self.driver = driver

    def __len__(self):
        return self.driver.run_js("return window.localStorage.length;")

    def items(self) -> dict:
        return self.driver.run_js(
            "var ls = window.localStorage, items = {}; "
            "for (var i = 0, k; i < ls.length; ++i) "
            "  items[k = ls.key(i)] = ls.getItem(k); "
            "return items; ")

    def keys(self):
        return self.driver.run_js(
            "var ls = window.localStorage, keys = []; "
            "for (var i = 0; i < ls.length; ++i) "
            "  keys[i] = ls.key(i); "
            "return keys; ")

    def get_item(self, key):
        return self.driver.run_js("return window.localStorage.getItem('{}');".format(key))

    def set_item(self, key, value):
        self.driver.run_js(
            "window.localStorage.setItem('{}', '{}');".format(key, value)
        )

    def has_item(self, key):
        return key in self.keys()

    def remove_item(self, key):
        self.driver.run_js(
            "window.localStorage.removeItem('{}');".format(key)
        )

    def clear(self):
        self.driver.run_js("window.localStorage.clear();")

    def __getitem__(self, key):
        value = self.get_item(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key, value):
        self.set_item(key, value)

    def __contains__(self, key):
        return key in self.keys()

    def __iter__(self):
        for x in self.items().items():
            yield x

    def __repr__(self):
        return self.items().__str__()