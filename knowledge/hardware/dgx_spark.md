# NVIDIA DGX Spark

## System Specifications
- OS: DGX OS 7.4.0
- Kernel: 6.17.0-1008-nvidia
- Architecture: ARM64 (Grace CPU)
- Memory: 128GB unified (CPU + GPU shared)
- Storage: NVMe SSD
- Network: mDNS accessible as spark-2b53.local

## CRITICAL WARNINGS
1. **DO NOT stop gdm3** - Crashes the entire system
   - gdm3 is pinned to version 46.0-2ubuntu1
   - Any upgrade/restart of gdm3 will hang the system
2. **Auto-updates disabled** - Manual updates only
   - apt auto-update service masked
3. **Locale**: May need LC_ALL=C for some operations

## Ollama Models
- qwen2.5:72b - Research, planning, analysis (primary)
- qwen2.5-coder:32b - Code generation (primary)
- nemotron:30b - Alternative reasoning model
- Models loaded into unified memory as needed
- Max 2 models simultaneously recommended

## Network
- mDNS hostname: spark-2b53.local
- Tailscale hostname: alpha-dgx-spark
- SSH: ssh zero@spark-2b53.local
- Ollama API: http://spark-2b53.local:11434

## GPU Memory Management
- Unified 128GB shared between CPU and GPU
- Ollama manages model loading/unloading
- Large models (72b) use ~45GB
- Medium models (32b) use ~20GB
- Small models (7b) use ~5GB
