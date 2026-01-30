import uuid
from typing import Optional, List, Dict, Any

from derisk._private.pydantic import BaseModel, Field


class AssetKnowledgeResponse(BaseModel):
    """Response model for knowledge assets."""
    asset_id: Optional[str] = Field(None,
                                    description="Unique identifier for the asset.")
    asset_type: Optional[str] = Field(None,
                                      description="Type of the asset (e.g., 'knowledge').")
    tags: Optional[List[str]] = Field(None, description="General category of the asset.")
    create_time: Optional[str] = Field(None,
                                            description="Timestamp when the asset was created.")
    update_time: Optional[str] = Field(None,
                                            description="Timestamp when the asset was last updated.")
    knowledge_type: Optional[str] = Field(None,
                                          description="Specific type of knowledge (e.g., 'document', 'FAQ').")
    knowledge_base_id: Optional[str] = Field(None,
                                             description="Identifier of the knowledge base this asset belongs to.")
    knowledge_base_name: Optional[str] = Field(None,
                                               description="Name of the knowledge base.")
    knowledge_base_desc: Optional[str] = Field(None,
                                               description="Description of the knowledge base.")
    highlight: Optional[dict] = Field(None, description="Highlighted text from the knowledge.")
    score: Optional[float] = Field(None, description="score.")



class AssetDocumentResponse(BaseModel):
    """Response model for knowledge assets."""
    asset_id: Optional[str] = Field(None,
                                    description="Unique identifier for the asset.")
    asset_type: Optional[str] = Field(None,
                                      description="Type of the asset (e.g., 'knowledge').")
    category: Optional[str] = Field(None, description="General category of the asset.")
    create_time: Optional[str] = Field(None,
                                            description="Timestamp when the asset was created.")
    update_time: Optional[str] = Field(None,
                                            description="Timestamp when the asset was last updated.")
    tags: Optional[List[str]] = Field(None,
                                      description="List of general tags associated with the asset.")
    knowledge_type: Optional[str] = Field(None,
                                          description="Specific type of knowledge (e.g., 'document', 'FAQ').")
    knowledge_base_id: Optional[str] = Field(None,
                                             description="Identifier of the knowledge base this asset belongs to.")
    knowledge_base_name: Optional[str] = Field(None,
                                               description="Name of the knowledge base.")
    knowledge_base_desc: Optional[str] = Field(None,
                                               description="Description of the knowledge base.")

    document_name: Optional[str] = Field(None, description="Name of the document.")
    document_id: Optional[str] = Field(None, description="Identifier of the document.")
    document_content: Optional[str] = Field(None,
                                            description="Content of the document.")
    document_tags: Optional[str] = Field(None,
                                               description="List of tags specific to the document.")
    document_type: Optional[str] = Field(None,
                                         description="Type of the document (e.g., 'pdf', 'word', 'markdown').")
    document_create_at: Optional[str] = Field(None,
                                                   description="Timestamp when the document was created.")
    document_update_at: Optional[str] = Field(None,
                                                   description="Timestamp when the document was last updated.")
    word_count: Optional[int] = Field(None, description="Size of the file in bytes.")
    document_link: Optional[str] = Field(None,
                                         description="Link or URL to the document.")
    creator: Optional[str] = Field(None, description="Creator of the document.")
    document_img_url: Optional[str] = Field(None, description="document_img_url")
    document_desc: Optional[str] = Field(None, description="document_desc")
    avatar_url: Optional[str] = Field(None, description="Avatar URL of the creator.")
    read_count: Optional[int] = Field(None, description="Number of times the document has been read.")
    like_count: Optional[int] = Field(None, description="Number of times the document has been favorited.")
    highlight: Optional[dict] = Field(None, description="Highlighted text from the document.")
    score: Optional[float] = Field(None, description="score.")

class AssetToolResponse(BaseModel): # New: Model for tool search results
    tool_id: Optional[str] = None
    tool_name: Optional[str] = None
    creator: Optional[str] = None
    tool_description: Optional[str] = None
    sub_tool_name: Optional[str] = None
    sub_tool_description: Optional[str] = None
    tool_type: Optional[str] = None
    tool_parameters: Optional[List[Dict]] = None # Or use your ToolParameterModel
    highlight: Dict[str, List[str]] = Field(default_factory=dict)
    score: Optional[float] = None
    asset_id: Optional[str] = Field(None,
                                    description="Unique identifier for the asset.")
    asset_type: Optional[str] = Field(None,
                                      description="Type of the asset (e.g., 'knowledge').")
    create_time: Optional[str] = Field(None,
                                       description="Timestamp when the asset was created.")
    update_time: Optional[str] = Field(None,
                                       description="Timestamp when the asset was last updated.")
    tags: Optional[List[str]] = Field(None,
                                      description="List of general tags associated with the asset.")

class AssetAgentRequest(BaseModel):
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    creator: Optional[str] = None
    avatar_url: Optional[str] = None
    agent_description: Optional[str] = None
    tags: Optional[List[str]] = Field(None,
                                      description="List of general tags associated with the asset.")


class AssetAgentResponse(BaseModel):
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    creator: Optional[str] = None
    avatar_url: Optional[str] = None
    agent_description: Optional[str] = None
    highlight: Dict[str, List[str]] = Field(default_factory=dict)
    score: Optional[float] = None
    asset_id: Optional[str] = Field(None,
                                    description="Unique identifier for the asset.")
    asset_type: Optional[str] = Field(None,
                                      description="Type of the asset (e.g., 'knowledge').")
    create_time: Optional[str] = Field(None,
                                       description="Timestamp when the asset was created.")
    update_time: Optional[str] = Field(None,
                                       description="Timestamp when the asset was last updated.")
    tags: Optional[List[str]] = Field(None,
                                      description="List of general tags associated with the asset.")

class FunctionScoreFieldFactor(BaseModel):
    """
    Field value factor for function_score
    """
    field: str
    modifier: str = "none" # e.g., "log1p", "sqrt"
    factor: float = 1.0
    missing: Optional[Any] = None

class FunctionScoreGauss(BaseModel):
    """
    Gauss function for function_score
    """
    field: str
    origin: str = "now" # or a date string
    scale: str
    offset: Optional[str] = None
    decay: Optional[float] = None

class RecommendationFunctionScoreConfig(BaseModel):
    field_value_factors: List[FunctionScoreFieldFactor] = Field(default_factory=list)
    gauss_functions: List[FunctionScoreGauss] = Field(default_factory=list)
    score_mode: str = "multiply" # e.g., "multiply", "avg", "sum", "first"
    boost_mode: str = "multiply" # e.g., "multiply", "replace", "sum", "avg", "max", "min"


class AssetKnowledgeSearchRequest(BaseModel):
    """Request model for querying knowledge assets."""
    # Fields for querying/filtering knowledge
    query: Optional[str] = Field(None, description="Specific asset ID to retrieve.")
    index_name: Optional[str] = Field(
        "derisk_search_assets_0825", description="Filter by index name."
    )
    tool_type: Optional[str] = Field(None, description="Filter by tool_type.")
    knowledge_type: Optional[str] = Field(None, description="Filter by knowledge type.")
    document_type: Optional[str] = Field(None, description="Filter by document type (e.g., 'pdf', 'md').")
    tags: Optional[List[str]] = Field(None, description="Filter by general asset tags.")
    document_tags: Optional[List[str]] = Field(None, description="Filter by document-specific tags.")
    limit: Optional[int] = Field(20, description="Maximum number of results to return.")
    top_k: Optional[int] = Field(10, description="Maximum number of results to return.")
    score_threshold: Optional[float] = Field(0.0, description="score of results to filter.")
    offset: Optional[int] = Field(0, description="Starting offset for results.")
    vector_boost: Optional[float] = Field(1.0, description="Boost for vector search.")
    vector_candidates: Optional[int] = Field(500, description="Candidates for vector search.")
    text_boost: Optional[float] = Field(2.0, description="Boost for text search.")
    knowledge_weight: Optional[float] = Field(3, description="")
    knowledge_desc_weight: Optional[float] = Field(1, description="Weight for knowledge search.")
    document_weight: Optional[float] = Field(3, description="Weight for document search.")
    agent_name_weight: Optional[float] = Field(3, description="Weight for agent search.")
    agent_desc_weight: Optional[float] = Field(3, description="Weight for agent desc search.")
    tool_name_weight: Optional[float] = Field(3, description="Weight for tool search.")
    tool_desc_weight: Optional[float] = Field(3, description="Weight for tool search.")
    tool_param_name_weight: Optional[float] = Field(1, description="Weight for tool search.")
    tool_param_desc_weight: Optional[float] = Field(1, description="Weight for tool search.")
    document_desc_weight: Optional[float] = Field(1, description="Weight for document search.")
    document_content_weight: Optional[float] = Field(1, description="Weight for document search.")
    tag_weight: Optional[float] = Field(4, description="Weight for tag search.")
    agent_type: Optional[str] = None
    page: Optional[int] = Field(1, description="Page number for pagination.")
    highlight_tag: Optional[str] = Field("{\"pre_tag\":\"<em>\",\"post_tag\":\"</em>\"}", description="Highlight tag.")
    multi_match_weights: Dict[str, float] = Field(default_factory=dict)
    match_phrase_fields_boost: Dict[str, float] = Field(
        default_factory=dict)  # field: boost
    function_score_config: Optional[RecommendationFunctionScoreConfig] = None
    # Fields to include in _source
    source_includes: Optional[List[str]] = None
    source_excludes: Optional[List[str]] = None
    rerank_model: Optional[str] = "derisk/bge-reranker-v2-m3"

class AssetKnowledgeCreateRequest(BaseModel):
    """Request model for creating knowledge assets."""
    knowledge_id: str = Field(None, description="Specific asset ID to create.")

class AssetDocumentRequest(BaseModel):
    """Request model for creating knowledge assets."""
    knowledge_id: str = Field(None, description="Specific asset ID to create.")
    document_id: str = Field(None, description="Specific asset ID to create.")
    document_content: str = Field(None, description="Specific asset ID to create.")
    document_type: str = Field(None, description="Specific asset ID to create.")
    document_link: str = Field(None, description="Specific asset ID to create.")
    creator: str = Field(None, description="Specific asset ID to create.")
    document_img_url: str = Field(None, description="Specific asset ID to create.")
    create_time: Optional[str] = None
    update_time: Optional[str] = None

class AssetToolRequest(BaseModel):
    """Request model for creating knowledge assets."""
    tool_id: str = Field(None, description="Specific asset ID to create.")
    asset_id: str = Field(
        str(f"asset-{uuid.uuid4()}"), description="Specific asset ID to create."
    )
    tool_name: Optional[str] = None
    creator: Optional[str] = None
    tool_description: Optional[str] = None
    sub_tool_name: Optional[str] = None
    sub_tool_description: Optional[str] = None
    tool_type: Optional[str] = None
    tool_parameters: Optional[List[Dict]] = None
    create_time: Optional[str] = None
    update_time: Optional[str] = None

