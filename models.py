from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class CloudProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class Runtime(str, Enum):
    PYTHON = "python3.11"
    NODEJS = "nodejs20.x"
    JAVA = "java17"
    GO = "go1.21"
    DOTNET = "dotnet8"


class TrafficPattern(str, Enum):
    STEADY = "steady"
    BURSTY = "bursty"
    SPIKY = "spiky"


class MemoryConfig(BaseModel):
    mb: int = Field(ge=128, le=10240)
    
    @property
    def gb(self) -> float:
        return self.mb / 1024.0


class PricingConfig(BaseModel):
    request_price_per_million: float
    compute_price_per_gb_second: float
    free_tier_requests_per_month: int
    free_tier_gb_seconds_per_month: int
    cpu_price_per_second: Optional[float] = None
    memory_price_per_gb_second: Optional[float] = None


class ColdStartConfig(BaseModel):
    base_cold_start_ms: dict[int, float] = Field(default_factory=dict)
    memory_scaling_factor: float = 1.0
    runtime_multipliers: dict[str, float] = Field(default_factory=dict)
    dependency_factor: float = 1.0
    vpc_penalty_ms: float = 0.0


class ProviderConfig(BaseModel):
    name: CloudProvider
    pricing: PricingConfig
    cold_start: ColdStartConfig
    memory_options: list[int] = Field(default_factory=list)
    max_timeout_seconds: int = 900
    supports_provisioned_concurrency: bool = False
    supports_min_instances: bool = False


class FunctionConfig(BaseModel):
    provider: CloudProvider
    runtime: Runtime
    memory_mb: int = Field(ge=128, le=10240)
    avg_duration_ms: int = Field(gt=0, le=900000)
    monthly_invocations: int = Field(ge=0)
    traffic_pattern: TrafficPattern = TrafficPattern.STEADY
    has_heavy_dependencies: bool = False
    uses_vpc: bool = False
    provisioned_concurrency: int = 0
    min_instances: int = 0


class SimulationResult(BaseModel):
    provider: CloudProvider
    memory_mb: int
    runtime: Runtime
    traffic_pattern: TrafficPattern
    
    cold_start_probability: float
    avg_cold_start_ms: float
    warm_duration_ms: int
    effective_duration_ms: float
    
    monthly_requests_cost: float
    monthly_compute_cost: float
    monthly_total_cost: float
    monthly_free_tier_savings: float
    
    cold_start_cost_overhead: float
    cost_per_invocation: float
    
    optimal_memory_mb: Optional[int] = None
    optimal_cost: Optional[float] = None
    savings_from_optimization: Optional[float] = None


class ComparisonResult(BaseModel):
    function_config: FunctionConfig
    results: list[SimulationResult]
    best_provider: CloudProvider
    best_cost: float
    worst_provider: CloudProvider
    worst_cost: float
    recommendation: str