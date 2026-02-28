from abc import ABC, abstractmethod


class BaseStorageService(ABC):
    @abstractmethod
    def upload_text(self, key: str, text: str) -> None: ...

    @abstractmethod
    def download_text(self, key: str) -> str: ...


class BaseEmbeddingService(ABC):
    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class BaseRerankerService(ABC):
    @abstractmethod
    async def rerank(self, query: str, chunks: list[dict], top_n: int = 5) -> list[dict]: ...


class BaseQueueService(ABC):
    @abstractmethod
    def enqueue(self, job: dict) -> None: ...

    @abstractmethod
    def poll(self, wait_seconds: int = 20) -> list[dict]: ...

    @abstractmethod
    def delete_message(self, receipt_handle: str) -> None: ...
