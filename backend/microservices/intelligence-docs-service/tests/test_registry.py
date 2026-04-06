import pytest
from app.providers.registry import ProviderRegistry
from app.providers.base import EmbeddingProvider


class FakeEmbeddingOK(EmbeddingProvider):
    name = "fake-ok"

    async def embed(self, texts, task=""):
        return [[0.1] * 10 for _ in texts]

    async def embed_single(self, text, task=""):
        return [0.1] * 10

    def dimensions(self):
        return 10

    async def is_available(self):
        return True


class FakeEmbeddingFail(EmbeddingProvider):
    name = "fake-fail"

    async def embed(self, texts, task=""):
        raise ConnectionError("down")

    async def embed_single(self, text, task=""):
        raise ConnectionError("down")

    def dimensions(self):
        return 10

    async def is_available(self):
        return False


@pytest.mark.asyncio
async def test_registry_returns_first_available():
    registry = ProviderRegistry[EmbeddingProvider]()
    registry.register(FakeEmbeddingFail())
    registry.register(FakeEmbeddingOK())
    provider = await registry.get_available()
    assert provider.name == "fake-ok"


@pytest.mark.asyncio
async def test_registry_raises_when_none_available():
    registry = ProviderRegistry[EmbeddingProvider]()
    registry.register(FakeEmbeddingFail())
    with pytest.raises(RuntimeError, match="No.*provider available"):
        await registry.get_available()


def test_registry_list_all():
    registry = ProviderRegistry[EmbeddingProvider]()
    ok = FakeEmbeddingOK()
    registry.register(ok)
    assert registry.all() == [ok]
