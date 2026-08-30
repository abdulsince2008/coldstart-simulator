from models import (
    ProviderConfig, PricingConfig, ColdStartConfig, CloudProvider, Runtime, MemoryConfig
)


AWS_PRICING = PricingConfig(
    request_price_per_million=0.20,
    compute_price_per_gb_second=0.0000166667,
    free_tier_requests_per_month=1_000_000,
    free_tier_gb_seconds_per_month=400_000,
)

AZURE_PRICING = PricingConfig(
    request_price_per_million=0.20,
    compute_price_per_gb_second=0.000016,
    free_tier_requests_per_month=1_000_000,
    free_tier_gb_seconds_per_month=400_000,
)

GCP_PRICING = PricingConfig(
    request_price_per_million=0.40,
    compute_price_per_gb_second=0.0,
    free_tier_requests_per_month=2_000_000,
    free_tier_gb_seconds_per_month=180_000,
    cpu_price_per_second=0.00002400,
    memory_price_per_gb_second=0.00000250,
)

AWS_COLD_START = ColdStartConfig(
    base_cold_start_ms={
        128: 450,
        256: 320,
        512: 200,
        1024: 130,
        2048: 90,
        3008: 70,
        4096: 60,
        6144: 55,
        8192: 50,
        10240: 45,
    },
    memory_scaling_factor=0.85,
    runtime_multipliers={
        "python3.11": 1.0,
        "nodejs20.x": 0.9,
        "java17": 2.5,
        "go1.21": 0.6,
        "dotnet8": 1.8,
    },
    dependency_factor=1.4,
    vpc_penalty_ms=150,
)

AZURE_COLD_START = ColdStartConfig(
    base_cold_start_ms={
        128: 550,
        256: 400,
        512: 280,
        1024: 180,
        1536: 140,
        2048: 120,
        3072: 100,
        4096: 90,
    },
    memory_scaling_factor=0.88,
    runtime_multipliers={
        "python3.11": 1.0,
        "nodejs20.x": 0.95,
        "java17": 3.0,
        "go1.21": 0.7,
        "dotnet8": 1.5,
    },
    dependency_factor=1.5,
    vpc_penalty_ms=200,
)

GCP_COLD_START = ColdStartConfig(
    base_cold_start_ms={
        128: 380,
        256: 250,
        512: 150,
        1024: 100,
        2048: 70,
        4096: 55,
        8192: 45,
        16384: 40,
        32768: 35,
    },
    memory_scaling_factor=0.82,
    runtime_multipliers={
        "python3.11": 1.0,
        "nodejs20.x": 0.85,
        "java17": 2.2,
        "go1.21": 0.5,
        "dotnet8": 1.6,
    },
    dependency_factor=1.3,
    vpc_penalty_ms=100,
)

PROVIDER_CONFIGS = {
    CloudProvider.AWS: ProviderConfig(
        name=CloudProvider.AWS,
        pricing=AWS_PRICING,
        cold_start=AWS_COLD_START,
        memory_options=[128, 256, 512, 1024, 2048, 3008, 4096, 6144, 8192, 10240],
        max_timeout_seconds=900,
        supports_provisioned_concurrency=True,
        supports_min_instances=False,
    ),
    CloudProvider.AZURE: ProviderConfig(
        name=CloudProvider.AZURE,
        pricing=AZURE_PRICING,
        cold_start=AZURE_COLD_START,
        memory_options=[128, 256, 512, 1024, 1536, 2048, 3072, 4096],
        max_timeout_seconds=600,
        supports_provisioned_concurrency=False,
        supports_min_instances=True,
    ),
    CloudProvider.GCP: ProviderConfig(
        name=CloudProvider.GCP,
        pricing=GCP_PRICING,
        cold_start=GCP_COLD_START,
        memory_options=[128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768],
        max_timeout_seconds=3600,
        supports_provisioned_concurrency=False,
        supports_min_instances=True,
    ),
}


def get_provider_config(provider: CloudProvider) -> ProviderConfig:
    return PROVIDER_CONFIGS[provider]


def get_available_memory(provider: CloudProvider) -> list[int]:
    return PROVIDER_CONFIGS[provider].memory_options