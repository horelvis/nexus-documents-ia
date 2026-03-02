"""
LangGraph ReAct Agent Nodes

Node implementations for the ReAct StateGraph.

Each node is an async function that:
1. Receives the current ReActState
2. Performs its operation (LLM call, tool execution, etc.)
3. Returns updates to the state

Execution Paths:
    Simple:  classify -> react_loop (loop) -> synthesize_react
    Complex: classify -> decompose -> swarm_worker (x N) -> synthesize_swarm
"""

from .classify import classify_node
from .react_loop import react_loop_node
from .synthesize_react import synthesize_react_node
from .decompose import decompose_node
from .swarm_worker import swarm_worker_node
from .synthesize_swarm import synthesize_swarm_node

__all__ = [
    "classify_node",
    "react_loop_node",
    "synthesize_react_node",
    "decompose_node",
    "swarm_worker_node",
    "synthesize_swarm_node",
]
