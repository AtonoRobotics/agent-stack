# Docker Issues

## MCP Server Suspension
- MCP server processes can enter suspended state (state T in ps aux)
- Cause: stdio transport hangs when parent process detaches
- Solution: Run as systemd user service with proper Type=simple
- Monitor with: ps aux | grep mcp

## Container Best Practices
- Always pin image tags (never use :latest in production)
- Use multi-stage builds for smaller images
- Mount volumes for persistent data, not COPY
- Use --gpus all for GPU-enabled containers
