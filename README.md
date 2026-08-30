# ColdStart Simulator

**Serverless Cold-Start Cost Simulator** — Simulate cold-start frequency and cost delta across AWS Lambda, GCP Cloud Functions, and Azure Functions. Get optimal memory recommendations for your workload.

## Problem Statement

Serverless functions incur hidden costs from cold starts that vary dramatically by cloud provider, memory allocation, runtime, and traffic pattern. Existing tools either calculate static pricing (Infracost) or measure cold starts in production (Lambda Power Tuning), but none simulate *how traffic patterns drive cold-start frequency* and *what that costs across all three major providers* — while recommending the optimal memory setting to minimize total cost.

## Why This Is Different

| Tool | Pricing | Cold Starts | Multi-Cloud | Memory Optimization | Traffic Patterns |
|------|---------|-------------|-------------|---------------------|------------------|
| **Infracost** | ✅ Real-time API | ❌ | ✅ | ❌ | ❌ |
| **AWS Lambda Power Tuning** | ✅ | ✅ (empirical) | ❌ AWS only | ✅ | ❌ |
| **Cloud provider calculators** | ✅ | ❌ | ❌ Single cloud | ❌ | ❌ |
| **This tool** | ✅ Modeled from public pricing | ✅ Simulated from benchmarks | ✅ AWS, GCP, Azure | ✅ Finds optimal MB | ✅ Steady/Bursty/Spiky |

**The one genuinely new piece**: A traffic-pattern-aware cold-start frequency model that feeds into per-provider cost calculations, enabling cross-cloud cost comparison *including* cold-start overhead — with memory optimization recommendations for each provider.

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Function Config │────▶│ Traffic Simulator │────▶│ Hourly Invocations
│ (runtime, mem,   │     │ (steady/bursty/  │     │ per month
│  duration, etc.) │     │  spiky patterns) │     └────────┬────────┘
└─────────────────┘     └──────────────────┘              │
                                                         ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Cost Calculator │◀───│ Cold-Start Model  │◀───│ Idle Timeout &  │
│ (per-provider    │     │ (benchmark-based │     │ Warm Pool Logic │
│  pricing + GB-s)  │     │  per runtime)    │     └─────────────────┘
└────────┬────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐
│  Memory Sweep   │
│  (finds optimal │
│   MB per cloud) │
└─────────────────┘
```

1. **Traffic Simulator** — Generates 720 hours of invocations using Poisson distributions modulated by pattern (steady = constant, bursty = daily peaks, spiky = rare huge spikes)
2. **Cold-Start Model** — Uses real benchmark data (Mikhail Shilkov, Prime Technologies, DevOpsBoys 2024-2026) for base cold-start latency per MB per runtime, scaled by dependencies, VPC, and memory
3. **Cost Engine** — Applies each provider's pricing model (AWS/Azure: GB-seconds; GCP: separate CPU-second + memory-second) with free-tier deductions
4. **Memory Optimizer** — Sweeps all valid memory sizes per provider, returns the MB minimizing total monthly cost

## Installation

```bash
git clone https://github.com/yourusername/coldstart-simulator
cd coldstart-simulator
pip install -r requirements.txt
```

## Usage

### Quick Start (CLI flags)

```bash
# Compare all 3 providers for a bursty Python API
python -m cli simulate \
  --provider aws \
  --runtime python3.11 \
  --memory 512 \
  --duration 200 \
  --invocations 10000000 \
  --pattern bursty \
  --heavy-deps

# With provisioned concurrency (AWS only)
python -m cli simulate -p aws -r python3.11 -m 512 -d 200 -i 10000000 --pattern bursty --provisioned 10

# JSON output for scripting
python -m cli simulate -p aws -r python3.11 -m 512 -d 200 -i 10000000 --pattern steady --output json
```

### Config File (recommended)

```bash
# Generate a sample config
python -m cli generate-sample -o my-config.yaml

# Edit my-config.yaml, then run:
python -m cli simulate -c my-config.yaml
```

**Sample config (`sample_config.yaml`):**
```yaml
provider: aws
runtime: python3.11
memory_mb: 512
avg_duration_ms: 200
monthly_invocations: 10000000
traffic_pattern: bursty
has_heavy_dependencies: true
uses_vpc: false
provisioned_concurrency: 0
min_instances: 0
```

### List Supported Providers

```bash
python -m cli providers
```

## Example Output

### Real Run: 10M invocations/month, Python 3.11, 512MB, bursty traffic, heavy deps

```
          AWS Lambda Simulation           
╭───────────────────────────┬────────────╮
│ Metric                    │      Value │
├───────────────────────────┼────────────┤
│ Runtime                   │ python3.11 │
│ Memory                    │     512 MB │
│ Traffic Pattern           │     Bursty │
│ Cold Start Probability    │       8.7% │
│ Avg Cold Start Latency    │     280 ms │
│ Warm Duration             │     282 ms │
│ Effective Duration        │     306 ms │
│                           │            │
│ Monthly Request Cost      │      $1.80 │
│ Monthly Compute Cost      │     $18.85 │
│ Monthly Total Cost        │     $20.65 │
│ Free Tier Savings         │      $6.87 │
│ Cold Start Overhead       │      $2.02 │
│ Cost per Invocation       │  $0.000002 │
│                           │            │
│ Optimal Memory            │     128 MB │
│ Optimal Cost              │      $8.04 │
│ Savings from Optimization │      61.1% │
╰───────────────────────────┴────────────╯

          GCP Cloud Functions Simulation           
╭───────────────────────────┬────────────╮
│ Metric                    │      Value │
├───────────────────────────┼────────────╮
│ Runtime                   │ python3.11 │
│ Memory                    │     512 MB │
│ Traffic Pattern           │     Bursty │
│ Cold Start Probability    │       8.7% │
│ Avg Cold Start Latency    │     195 ms │
│ Warm Duration             │     282 ms │
│ Effective Duration        │     299 ms │
│                           │            │
│ Monthly Request Cost      │      $3.20 │
│ Monthly Compute Cost      │     $66.65 │
│ Monthly Total Cost        │     $69.85 │
│ Free Tier Savings         │      $5.57 │
│ Cold Start Overhead       │    $0.2111 │
│ Cost per Invocation       │  $0.000007 │
│                           │            │
│ Optimal Memory            │    1024 MB │
│ Optimal Cost              │     $51.71 │
│ Savings from Optimization │      26.0% │
╰───────────────────────────┴────────────╯

         Azure Functions Simulation          
╭───────────────────────────┬────────────╮
│ Metric                    │      Value │
├───────────────────────────┼────────────╮
│ Runtime                   │ python3.11 │
│ Memory                    │     512 MB │
│ Traffic Pattern           │     Bursty │
│ Cold Start Probability    │       8.7% │
│ Avg Cold Start Latency    │     420 ms │
│ Warm Duration             │     282 ms │
│ Effective Duration        │     318 ms │
│                           │            │
│ Monthly Request Cost      │      $1.80 │
│ Monthly Compute Cost      │     $19.07 │
│ Monthly Total Cost        │     $20.87 │
│ Free Tier Savings         │      $6.60 │
│ Cold Start Overhead       │      $2.91 │
│ Cost per Invocation       │  $0.000002 │
│                           │            │
│ Optimal Memory            │     128 MB │
│ Optimal Cost              │      $8.13 │
│ Savings from Optimization │      61.0% │
╰───────────────────────────┴────────────╯

╭──────────────────────────── Provider Comparison ─────────────────────────────╮
│ Best: AWS ($20.65/month)                                                     │
│ Worst: GCP ($69.85/month)                                                    │
│                                                                              │
│ For bursty traffic, AWS is 70% cheaper. Provisioned concurrency on AWS can   │
│ help if cold starts >300ms.                                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
                                  Cost Summary                                  
╭──────────┬────────┬───────────┬───────────┬───────────┬────────────┬─────────╮
│          │        │      Cold │   Monthly │           │    Optimal │         │
│ Provider │ Memory │   Start % │      Cost │  Cost/Inv │        Mem │ Savings │
├──────────┼────────┼───────────┼───────────┼───────────┼────────────┼─────────┤
│ AWS      │ 512 MB │      8.7% │    $20.65 │ $0.000002 │     128 MB │   61.1% │
│ GCP      │ 512 MB │      8.7% │    $69.85 │ $0.000007 │    1024 MB │   26.0% │
│ AZURE    │ 512 MB │      8.7% │    $20.87 │ $0.000002 │     128 MB │   61.0% │
╰──────────┴────────┴───────────┴───────────┴───────────┴────────────┴─────────╯
```

### With Provisioned Concurrency (10 pre-warmed instances)

```
          AWS Lambda Simulation           
╭───────────────────────────┬────────────╮
│ Metric                    │      Value │
├───────────────────────────┼────────────╮
│ Cold Start Probability    │       2.2% │  ← dropped from 8.7%
│ Cold Start Overhead       │    $0.5034 │  ← dropped from $2.02
│ Monthly Total Cost        │     $19.14 │  ← modest savings
│ Optimal Memory            │     128 MB │
│ Savings from Optimization │      62.4% │
╰───────────────────────────┴────────────╯
```

### Java 17, 5M invocations, steady traffic (high cold starts)

```
╭──────────────────────────── Provider Comparison ─────────────────────────────╮
│ Best: AWS ($41.26/month)                                                     │
│ Worst: GCP ($63.20/month)                                                    │
│                                                                              │
│ For steady traffic, AWS is optimal. Memory tuning saves up to 73%.           │
╰──────────────────────────────────────────────────────────────────────────────╯
                                  Cost Summary                                  
╭──────────┬─────────┬───────────┬───────────┬───────────┬───────────┬─────────╮
│          │         │      Cold │   Monthly │           │   Optimal │         │
│ Provider │  Memory │   Start % │      Cost │  Cost/Inv │       Mem │ Savings │
├──────────┼─────────┼───────────┼───────────┼───────────┼───────────┼─────────╤
│ AWS      │ 1024 MB │     14.4% │    $41.26 │ $0.000008 │    128 MB │   72.8% │
│ GCP      │ 1024 MB │     14.4% │    $63.20 │ $0.000013 │   1024 MB │    0.0% │
│ AZURE    │ 1024 MB │     14.4% │    $43.74 │ $0.000009 │    128 MB │   72.3% │
╰──────────┴─────────┴───────────┴───────────┴───────────┴───────────┴─────────╯
```

## Tech Stack & Libraries Reused

| Library | Purpose | Why Not Custom |
|---------|---------|----------------|
| **requests** | HTTP client (for future pricing API integration) | Standard, battle-tested |
| **click** | CLI framework | Declarative, composable, zero-boilerplate |
| **rich** | Terminal tables, panels, colors | Beautiful output without ANSI wrangling |
| **pydantic** | Config validation & serialization | Type-safe config with automatic parsing |
| **numpy** | Poisson traffic simulation | Fast, statistically correct random generation |
| **pyyaml** | Config file parsing | Human-readable, supports comments |

**Pricing data**: Hardcoded from public 2024-2026 rate cards (AWS, Azure, GCP). *Future: Infracost Cloud Pricing API integration for live prices.*

**Cold-start benchmarks**: Synthesized from Mikhail Shilkov (2018-2024), Prime Technologies Global (Apr 2026), DevOpsBoys (May 2026), Telnyx (Jul 2026), and vendor documentation.

## Known Limitations / What's Next

- **Pricing is static** — not fetching live rates. Next: integrate Infracost Cloud Pricing API (GraphQL) for always-current prices across 3M+ SKUs.
- **Cold-start model is parametric** — not empirical per-function. Next: accept optional real-world `Init Duration` samples to calibrate the model.
- **No provisioned concurrency cost model** — AWS Provisioned Concurrency pricing ($0.0000646/GB-s) not yet subtracted from savings calc.
- **Single-function scope** — doesn't model fan-out, step functions, or multi-function apps.
- **No edge/Cloudflare Workers** — different architecture (V8 isolates, no cold starts). Could add as a fourth "provider" for comparison.
- **Assumes 10-min idle timeout** — configurable but not per-provider validated.

## License

MIT — see [LICENSE](LICENSE)