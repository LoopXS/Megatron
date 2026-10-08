from .. import udB


class KeyManager:
    def __init__(self, key, cast=None) -> None:
        self._key = key
        self._cast = cast

    def get(self):
        _data = udB.get_key(self._key)
        if _data is None:
            return [] if self._cast == list else self._cast()
        if self._cast == list and not isinstance(_data, list):
            return [_data]
        return _data
    
    def get_child(self, key):
        data = self.get()
        return data[key] if data is not None else None

    def count(self):
        data = self.get()
        return len(data) if data else 0

    def contains(self, item):
        content = self.get()
        return bool(content) and item in content 

    def add(self, item):
        content = self.get()
        if content == None and callable(type(item)):
            content = type(item)()
        if isinstance(content, dict) and isinstance(item, dict):
            content.update(item)
        elif isinstance(content, list) and item not in content:
            content.append(item)
        else:
            return
        udB.set_key(self._key, content)

    def remove(self, item):
        content = self.get()
        if isinstance(content, list) and item in content:
            content.remove(item)
        elif isinstance(content, dict) and content.get(item):
            del content[item]
        else:
            return
        udB.set_key(self._key, content)
