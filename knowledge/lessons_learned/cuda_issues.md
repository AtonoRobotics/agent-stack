# CUDA Issues

## Cross-Architecture Conflicts
- DGX Spark is ARM64 with different CUDA stack than x86 workstation
- Cannot share compiled CUDA extensions between architectures
- Always build CUDA extensions on the target architecture
- Container images must match architecture: linux/arm64 vs linux/amd64

## Common CUDA Errors
- "CUDA out of memory": Reduce batch size or scene complexity
- "CUDA driver version insufficient": Check nvidia-smi version matches
- "cuDNN version mismatch": Ensure PyTorch wheel matches CUDA version

## Version Matrix (Current)
| Machine     | CUDA  | cuDNN | PyTorch |
|-------------|-------|-------|---------|
| Workstation | 12.6  | 9.x   | 2.5     |
| DGX Spark   | 12.8  | 9.x   | 2.5     |
| AGX Thor    | 12.6  | 9.x   | 2.5     |
