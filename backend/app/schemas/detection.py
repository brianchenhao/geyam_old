from pydantic import BaseModel


class Detection(BaseModel):
    label: str
    name: str
    price: float
    confidence: float


class DetectionResponse(BaseModel):
    detections: list[Detection]
    total: float
