"""Bounded immutable file bytes shared by streaming capture, catalogue and staging."""

from collections import OrderedDict
from collections.abc import Mapping


class SourcePool:
    def __init__(self, cache, limit=24 * 1024 * 1024):
        self.cache, self.limit = cache, limit
        self.items = OrderedDict()
        self.size = 0

    def read(self, digest, size):
        key = digest, size
        if key in self.items:
            self.items.move_to_end(key)
            return self.items[key]
        data = self.cache.read(digest, size)
        while self.items and self.size + size > self.limit:
            _, old = self.items.popitem(last=False)
            self.size -= len(old)
        if size <= self.limit:
            self.items[key] = data
            self.size += len(data)
        return data


class CachedSource:
    def __init__(self, descriptor, live_path, pool):
        self._descriptor, self.live_path, self.pool = descriptor, live_path, pool
        self.source_kind, self.source_id, self.relative_path = descriptor.key

    @property
    def data(self):
        return self.pool.read(self._descriptor.file_sha256, self._descriptor.size)

    def descriptor(self):
        return self._descriptor


class SourceBytes(Mapping):
    def __init__(self, sources):
        self.sources = {source.descriptor().key: source for source in sources}

    def __getitem__(self, key):
        return self.sources[key].data

    def __iter__(self):
        return iter(self.sources)

    def __len__(self):
        return len(self.sources)
