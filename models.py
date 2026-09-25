from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, EmailStr, field_validator

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: str

class RecommendationItem(BaseModel):
    item_name: str
    category: str
    estimated_price: float
    platform: str
    why_it_fits: str
    product_search_link: str

class HomePlannerRequest(BaseModel):
    budget: float = Field(..., gt=0, description="Total budget in currency units (e.g. INR / USD)")
    room_types: List[str] = Field(..., min_length=1, description="Selected room types")
    items: Dict[str, int] = Field(default_factory=dict, description="Quantities of furniture/fixtures")
    style_preference: Optional[str] = Field("Modern Contemporary", description="Style preference")

class PartyPlannerRequest(BaseModel):
    budget: float = Field(..., gt=0, description="Total party budget")
    guest_count: int = Field(..., gt=0, description="Number of expected guests")
    event_type: str = Field(..., min_length=1, description="Event type: Birthday, Corporate, Wedding, etc.")
    venue_details: str = Field(..., min_length=1, description="Venue type or location description")
    special_notes: Optional[str] = Field("", description="Special dietary or thematic requirements")

class JewelryPlannerRequest(BaseModel):
    budget: float = Field(..., gt=0, description="Total jewelry budget")
    occasion: str = Field(..., min_length=1, description="Occasion: Wedding, Casual, Party, etc.")
    style_preference: str = Field(..., min_length=1, description="Style: Traditional, Minimalist, Royal, etc.")
    metal_preference: Optional[str] = Field("Any", description="Gold, Silver, Platinum, Diamond, Imitation")

class PlannerResponse(BaseModel):
    planner_type: str
    budget: float
    total_cost: float
    budget_status: str
    summary: str
    recommendations: List[RecommendationItem]
    history_id: Optional[int] = None
