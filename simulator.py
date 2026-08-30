from typing import Optional
import numpy as np
from models import (
    FunctionConfig, SimulationResult, ProviderConfig, CloudProvider,
    Runtime, TrafficPattern
)
from providers import get_provider_config, get_available_memory
from traffic import simulate_invocations, calculate_cold_start_probability


class ColdStartCostSimulator:
    def __init__(self, config: FunctionConfig):
        self.config = config
        self.provider_config = get_provider_config(config.provider)
        self.pricing = self.provider_config.pricing
        self.cold_start_config = self.provider_config.cold_start
    
    def calculate_cold_start_ms(self, memory_mb: int) -> float:
        base_cs = self.cold_start_config.base_cold_start_ms
        
        if memory_mb in base_cs:
            base = base_cs[memory_mb]
        else:
            sorted_mem = sorted(base_cs.keys())
            for i, m in enumerate(sorted_mem):
                if memory_mb < m:
                    if i == 0:
                        base = base_cs[m]
                    else:
                        lower = sorted_mem[i-1]
                        upper = m
                        ratio = (memory_mb - lower) / (upper - lower)
                        base = base_cs[lower] * (1 - ratio) + base_cs[upper] * ratio
                    break
            else:
                base = base_cs[sorted_mem[-1]]
        
        runtime_mult = self.cold_start_config.runtime_multipliers.get(
            self.config.runtime.value, 1.0
        )
        dep_factor = self.cold_start_config.dependency_factor if self.config.has_heavy_dependencies else 1.0
        vpc_penalty = self.cold_start_config.vpc_penalty_ms if self.config.uses_vpc else 0.0
        
        return base * runtime_mult * dep_factor + vpc_penalty
    
    def calculate_warm_duration_ms(self, memory_mb: int) -> int:
        base_duration = self.config.avg_duration_ms
        memory_ratio = memory_mb / 1024.0
        cpu_scaling = max(0.3, min(1.0, memory_ratio ** 0.5))
        return int(base_duration / cpu_scaling)
    
    def calculate_monthly_cost(
        self,
        memory_mb: int,
        cold_start_prob: float,
        avg_cold_start_ms: float,
        warm_duration_ms: int
    ) -> tuple[float, float, float, float, float, float]:
        invocations = self.config.monthly_invocations
        if invocations == 0:
            return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        
        effective_duration_ms = warm_duration_ms + (cold_start_prob * avg_cold_start_ms)
        effective_duration_s = effective_duration_ms / 1000.0
        warm_duration_s = warm_duration_ms / 1000.0
        
        memory_gb = memory_mb / 1024.0
        
        if self.config.provider == CloudProvider.GCP:
            cpu_seconds = invocations * warm_duration_s
            memory_gb_seconds = invocations * effective_duration_s * memory_gb
            
            request_cost = max(0, invocations - self.pricing.free_tier_requests_per_month) * \
                          self.pricing.request_price_per_million / 1_000_000
            cpu_cost = max(0, cpu_seconds - self.pricing.free_tier_gb_seconds_per_month) * \
                       self.pricing.cpu_price_per_second
            memory_cost = max(0, memory_gb_seconds - self.pricing.free_tier_gb_seconds_per_month) * \
                          self.pricing.memory_price_per_gb_second
            
            compute_cost = cpu_cost + memory_cost
        else:
            gb_seconds = invocations * effective_duration_s * memory_gb
            
            request_cost = max(0, invocations - self.pricing.free_tier_requests_per_month) * \
                          self.pricing.request_price_per_million / 1_000_000
            compute_cost = max(0, gb_seconds - self.pricing.free_tier_gb_seconds_per_month) * \
                          self.pricing.compute_price_per_gb_second
        
        total_cost = request_cost + compute_cost
        free_tier_savings = (min(invocations, self.pricing.free_tier_requests_per_month) * \
                           self.pricing.request_price_per_million / 1_000_000)
        
        if self.config.provider != CloudProvider.GCP:
            free_tier_gb_s = min(invocations * warm_duration_s * memory_gb, 
                                self.pricing.free_tier_gb_seconds_per_month)
            free_tier_savings += free_tier_gb_s * self.pricing.compute_price_per_gb_second
        else:
            free_tier_cpu = min(invocations * warm_duration_s, self.pricing.free_tier_gb_seconds_per_month)
            free_tier_savings += free_tier_cpu * self.pricing.cpu_price_per_second
            free_tier_mem = min(invocations * warm_duration_s * memory_gb, self.pricing.free_tier_gb_seconds_per_month)
            free_tier_savings += free_tier_mem * self.pricing.memory_price_per_gb_second
        
        cold_start_overhead = cold_start_prob * avg_cold_start_ms / 1000.0 * memory_gb * \
                             self.pricing.compute_price_per_gb_second * invocations
        if self.config.provider == CloudProvider.GCP:
            cold_start_overhead = cold_start_prob * avg_cold_start_ms / 1000.0 * memory_gb * \
                                 self.pricing.memory_price_per_gb_second * invocations
        
        cost_per_invocation = total_cost / invocations if invocations > 0 else 0.0
        
        return request_cost, compute_cost, total_cost, free_tier_savings, cold_start_overhead, cost_per_invocation
    
    def simulate(self, memory_mb: Optional[int] = None) -> SimulationResult:
        mem = memory_mb or self.config.memory_mb
        
        hourly_invocations = simulate_invocations(self.config)
        cold_start_prob = calculate_cold_start_probability(
            hourly_invocations,
            self.config.avg_duration_ms,
            self.config.provisioned_concurrency,
            self.config.min_instances
        )
        
        avg_cold_start_ms = self.calculate_cold_start_ms(mem)
        warm_duration_ms = self.calculate_warm_duration_ms(mem)
        effective_duration_ms = warm_duration_ms + (cold_start_prob * avg_cold_start_ms)
        
        req_cost, comp_cost, total_cost, free_savings, cs_overhead, cost_per_inv = \
            self.calculate_monthly_cost(mem, cold_start_prob, avg_cold_start_ms, warm_duration_ms)
        
        return SimulationResult(
            provider=self.config.provider,
            memory_mb=mem,
            runtime=self.config.runtime,
            traffic_pattern=self.config.traffic_pattern,
            cold_start_probability=cold_start_prob,
            avg_cold_start_ms=avg_cold_start_ms,
            warm_duration_ms=warm_duration_ms,
            effective_duration_ms=effective_duration_ms,
            monthly_requests_cost=req_cost,
            monthly_compute_cost=comp_cost,
            monthly_total_cost=total_cost,
            monthly_free_tier_savings=free_savings,
            cold_start_cost_overhead=cs_overhead,
            cost_per_invocation=cost_per_inv,
        )
    
    def find_optimal_memory(self) -> tuple[int, float, float]:
        available_memory = get_available_memory(self.config.provider)
        best_memory = self.config.memory_mb
        best_cost = float('inf')
        baseline_cost = None
        
        for mem in available_memory:
            if mem > self.provider_config.max_timeout_seconds * 100:
                continue
            result = self.simulate(mem)
            if result.monthly_total_cost < best_cost:
                best_cost = result.monthly_total_cost
                best_memory = mem
            if mem == self.config.memory_mb:
                baseline_cost = result.monthly_total_cost
        
        savings = 0.0
        if baseline_cost and baseline_cost > 0:
            savings = ((baseline_cost - best_cost) / baseline_cost) * 100
        
        return best_memory, best_cost, savings
    
    def run_full_analysis(self) -> SimulationResult:
        result = self.simulate()
        optimal_mem, optimal_cost, savings = self.find_optimal_memory()
        
        result.optimal_memory_mb = optimal_mem
        result.optimal_cost = optimal_cost
        result.savings_from_optimization = savings
        
        return result


def simulate_all_providers(config: FunctionConfig) -> list[SimulationResult]:
    results = []
    for provider in CloudProvider:
        provider_config = FunctionConfig(
            provider=provider,
            runtime=config.runtime,
            memory_mb=config.memory_mb,
            avg_duration_ms=config.avg_duration_ms,
            monthly_invocations=config.monthly_invocations,
            traffic_pattern=config.traffic_pattern,
            has_heavy_dependencies=config.has_heavy_dependencies,
            uses_vpc=config.uses_vpc,
            provisioned_concurrency=config.provisioned_concurrency if provider == CloudProvider.AWS else 0,
            min_instances=config.min_instances if provider in [CloudProvider.AZURE, CloudProvider.GCP] else 0,
        )
        simulator = ColdStartCostSimulator(provider_config)
        result = simulator.run_full_analysis()
        results.append(result)
    return results