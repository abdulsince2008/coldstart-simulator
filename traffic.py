import numpy as np
from typing import List
from models import TrafficPattern, FunctionConfig


def simulate_invocations(
    config: FunctionConfig,
    hours: int = 720,
    seed: int = 42
) -> List[int]:
    np.random.seed(seed)
    invocations_per_hour = config.monthly_invocations / hours
    
    if config.traffic_pattern == TrafficPattern.STEADY:
        return _steady_pattern(invocations_per_hour, hours)
    elif config.traffic_pattern == TrafficPattern.BURSTY:
        return _bursty_pattern(invocations_per_hour, hours)
    elif config.traffic_pattern == TrafficPattern.SPIKY:
        return _spiky_pattern(invocations_per_hour, hours)
    else:
        return _steady_pattern(invocations_per_hour, hours)


def _steady_pattern(base_rate: float, hours: int) -> List[int]:
    hourly = np.random.poisson(base_rate, hours)
    return hourly.tolist()


def _bursty_pattern(base_rate: float, hours: int) -> List[int]:
    burst_hours = max(1, hours // 24)
    burst_multiplier = 20.0
    normal_rate = base_rate / (1 + (burst_multiplier - 1) * burst_hours / hours)
    burst_rate = normal_rate * burst_multiplier
    
    is_burst = np.random.choice([False, True], size=hours, p=[1 - burst_hours/hours, burst_hours/hours])
    rates = np.where(is_burst, burst_rate, normal_rate)
    hourly = np.random.poisson(rates)
    return hourly.tolist()


def _spiky_pattern(base_rate: float, hours: int) -> List[int]:
    spike_probability = 0.05
    spike_multiplier = 100.0
    normal_rate = base_rate / (1 + (spike_multiplier - 1) * spike_probability)
    spike_rate = normal_rate * spike_multiplier
    
    is_spike = np.random.choice([False, True], size=hours, p=[1 - spike_probability, spike_probability])
    rates = np.where(is_spike, spike_rate, normal_rate)
    hourly = np.random.poisson(rates)
    return hourly.tolist()


def calculate_cold_start_probability(
    hourly_invocations: List[int],
    avg_duration_ms: int,
    provisioned_concurrency: int = 0,
    min_instances: int = 0,
    max_concurrent: int = 1000,
    idle_timeout_minutes: int = 10
) -> float:
    warm_pool = provisioned_concurrency + min_instances
    total_invocations = sum(hourly_invocations)
    
    if total_invocations == 0:
        return 0.0
    
    cold_starts = 0
    current_warm = warm_pool
    last_active_hour = -idle_timeout_minutes // 60 - 1
    
    for hour_idx, hour_invocations in enumerate(hourly_invocations):
        hours_since_active = hour_idx - last_active_hour
        
        if hour_invocations == 0:
            if hours_since_active * 60 >= idle_timeout_minutes and current_warm > warm_pool:
                current_warm = warm_pool
            continue
        
        last_active_hour = hour_idx
        concurrent_needed = max(1, hour_invocations * avg_duration_ms / 3_600_000)
        concurrent_needed = min(concurrent_needed, max_concurrent)
        
        if current_warm >= concurrent_needed:
            current_warm = concurrent_needed
        else:
            new_instances = concurrent_needed - current_warm
            cold_starts += new_instances
            current_warm = concurrent_needed
        
        if current_warm > warm_pool:
            current_warm = max(warm_pool, int(current_warm * 0.95))
    
    if warm_pool == 0:
        active_hours = sum(1 for h in hourly_invocations if h > 0)
        if active_hours > 0:
            cold_starts = max(cold_starts, active_hours)
    
    return min(1.0, cold_starts / max(1, total_invocations / 1000))


def get_traffic_pattern_description(pattern: TrafficPattern) -> str:
    descriptions = {
        TrafficPattern.STEADY: "Constant request rate throughout the month",
        TrafficPattern.BURSTY: "Periodic traffic bursts (e.g., daily peaks, scheduled jobs)",
        TrafficPattern.SPIKY: "Unpredictable traffic spikes (e.g., viral content, flash sales)",
    }
    return descriptions.get(pattern, "Unknown pattern")