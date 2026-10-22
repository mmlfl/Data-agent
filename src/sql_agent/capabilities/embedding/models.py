class EncodeQuery(BaseModel):
    dense: list[float]
    sparse: list[dict[str,float]] = Field(default_factory=list)

class EncodeBatch(BaseModel):
    dense: list[list[float]] = Field(default_factory=list)
    sparse:list[dict[str,float]] = Field(default_factory=list)