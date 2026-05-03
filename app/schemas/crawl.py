from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    platform: str = Field(..., description="Platform to search on (e.g. youtube, reddit)")
    keyword: str = Field(..., description="Keyword to search for")
    limit: int = Field(20, description="Maximum number of results to fetch")
