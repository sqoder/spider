from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    platform: str = Field(..., description="Platform to search on (e.g. youtube, reddit)")
    keyword: str = Field(..., description="Keyword to search for")
    limit: int = Field(20, description="Maximum number of results to fetch")
    deep: bool = Field(False, description="Whether to perform a comprehensive 'no blind spot' crawl for every result")

class DetailRequest(BaseModel):
    platform: str = Field(..., description="Platform to extract from")
    url: str = Field(..., description="URL of the post to comprehensively extract")
