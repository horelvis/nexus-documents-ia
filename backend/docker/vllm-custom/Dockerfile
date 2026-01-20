# =============================================================================
# vLLM Custom Image - Extended transformers support
# =============================================================================
# Base: vllm/vllm-openai:latest
# Extension: transformers >= 4.57.0 (required for Qwen3 models)
#
# This image is used for both:
#   - vllm service (LLM inference)
#   - qwen3-vl-embedding service (multimodal embeddings)
#
# The transformers upgrade enables support for newer model architectures
# while maintaining full vLLM OpenAI-compatible API compatibility.
# =============================================================================
FROM vllm/vllm-openai:latest

# Install git (required for pip install from GitHub if needed)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade transformers for Qwen3 model support
# Qwen3 models require transformers >= 4.57.0
RUN pip install --no-cache-dir "transformers>=4.57.0,<5.0.0" || \
    pip install --no-cache-dir git+https://github.com/huggingface/transformers@v4.57-release

# Verify installation
RUN python3 -c "import transformers; print(f'Transformers version: {transformers.__version__}')"
