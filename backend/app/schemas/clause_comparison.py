from pydantic import BaseModel


class ClauseComparisonExport(BaseModel):
    query: str
    language: str = "es"
    results: list[dict]
    missing: list[dict]
