from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from loguru import logger
import re

from app.schemas.graph import GraphNode


class TagState(TypedDict):
    """State for tag generation graph"""
    text: str
    max_tags: int
    tag_type: str
    raw_tags: Optional[List[str]]
    validated_tags: Optional[List[str]]
    confidence_scores: Optional[Dict[str, float]]
    reasoning: Optional[str]
    needs_refinement: bool
    iteration: int


class TagGenerationGraph:
    """Graph for generating tags from text using LangGraph"""
    
    def __init__(self, llm, embeddings, qdrant_client, checkpointer, **kwargs):
        self.llm = llm
        self.embeddings = embeddings
        self.qdrant_client = qdrant_client
        self.checkpointer = checkpointer
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the tag generation graph"""
        workflow = StateGraph(TagState)
        
        # Add nodes
        workflow.add_node("generate_tags", self.generate_tags)
        workflow.add_node("validate_tags", self.validate_tags)
        workflow.add_node("calculate_confidence", self.calculate_confidence)
        workflow.add_node("refine_tags", self.refine_tags)
        
        # Set entry point
        workflow.set_entry_point("generate_tags")
        
        # Add edges
        workflow.add_edge("generate_tags", "validate_tags")
        workflow.add_edge("validate_tags", "calculate_confidence")
        
        # Conditional edge for refinement
        workflow.add_conditional_edges(
            "calculate_confidence",
            self.should_refine,
            {
                "refine": "refine_tags",
                "done": END
            }
        )
        
        # Edge from refine back to validate
        workflow.add_edge("refine_tags", "validate_tags")
        
        # Compile with checkpointer
        return workflow.compile(checkpointer=self.checkpointer)
    
    async def generate_tags(self, state: TagState) -> TagState:
        """Generate initial tags from text"""
        logger.info(f"Generating tags for text of length {len(state['text'])}")
        
        # Create prompt based on tag type
        prompts = {
            "general": "Extract the most relevant tags from the following text. Focus on main topics, themes, and key concepts.",
            "technical": "Extract technical tags from the following text. Focus on technologies, frameworks, methods, and technical concepts.",
            "business": "Extract business-related tags from the following text. Focus on business terms, strategies, departments, and processes."
        }
        
        prompt = prompts.get(state.get("tag_type", "general"), prompts["general"])
        
        messages = [
            HumanMessage(content=f"""
{prompt}

Rules:
1. Generate exactly {state['max_tags']} tags
2. Tags should be concise (1-3 words)
3. Use lowercase
4. No special characters except hyphens
5. Order by relevance

Text: {state['text'][:1000]}...

Return only the tags as a comma-separated list.
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        raw_tags = [tag.strip().lower() for tag in response.content.split(",")]
        
        state["raw_tags"] = raw_tags[:state["max_tags"]]
        state["iteration"] = state.get("iteration", 0) + 1
        
        return state
    
    async def validate_tags(self, state: TagState) -> TagState:
        """Validate and clean tags"""
        logger.info("Validating tags")
        
        validated_tags = []
        for tag in state.get("raw_tags", []):
            # Clean tag
            tag = re.sub(r'[^a-z0-9\s-]', '', tag.lower())
            tag = re.sub(r'\s+', '-', tag.strip())
            
            # Validate length and format
            if 2 <= len(tag) <= 30 and tag not in validated_tags:
                validated_tags.append(tag)
        
        state["validated_tags"] = validated_tags[:state["max_tags"]]
        
        # Check if we have enough valid tags
        if len(validated_tags) < state["max_tags"]:
            state["needs_refinement"] = True
        else:
            state["needs_refinement"] = False
        
        return state
    
    async def calculate_confidence(self, state: TagState) -> TagState:
        """Calculate confidence scores for tags"""
        logger.info("Calculating confidence scores")
        
        if not state.get("validated_tags"):
            return state
        
        # Simple confidence calculation based on tag appearance in text
        confidence_scores = {}
        text_lower = state["text"].lower()
        
        for tag in state["validated_tags"]:
            # Check variations of the tag
            tag_words = tag.replace("-", " ")
            count = text_lower.count(tag_words)
            
            # Calculate confidence (0.3 to 1.0)
            if count > 5:
                confidence = 1.0
            elif count > 2:
                confidence = 0.8
            elif count > 0:
                confidence = 0.6
            else:
                confidence = 0.3  # Base confidence for AI-generated tags
            
            confidence_scores[tag] = confidence
        
        state["confidence_scores"] = confidence_scores
        
        # Add reasoning
        avg_confidence = sum(confidence_scores.values()) / len(confidence_scores)
        state["reasoning"] = f"Generated {len(state['validated_tags'])} tags with average confidence {avg_confidence:.2f}"
        
        return state
    
    async def refine_tags(self, state: TagState) -> TagState:
        """Refine tags if needed"""
        logger.info("Refining tags")
        
        # Check iteration limit
        if state.get("iteration", 0) >= 3:
            state["needs_refinement"] = False
            return state
        
        current_tags = state.get("validated_tags", [])
        needed = state["max_tags"] - len(current_tags)
        
        messages = [
            HumanMessage(content=f"""
The following tags were generated but we need {needed} more tags:
Current tags: {', '.join(current_tags)}

Generate {needed} additional unique tags from this text that are different from the existing ones:
{state['text'][:500]}...

Return only the new tags as a comma-separated list.
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        new_tags = [tag.strip().lower() for tag in response.content.split(",")]
        
        # Combine with existing tags
        state["raw_tags"] = current_tags + new_tags
        
        return state
    
    def should_refine(self, state: TagState) -> str:
        """Determine if refinement is needed"""
        if state.get("needs_refinement", False) and state.get("iteration", 0) < 3:
            return "refine"
        return "done"
    
    async def ainvoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None):
        """Invoke the graph"""
        # Initialize state
        initial_state = TagState(
            text=input_data.get("text", ""),
            max_tags=input_data.get("max_tags", 5),
            tag_type=input_data.get("tag_type", "general"),
            raw_tags=None,
            validated_tags=None,
            confidence_scores=None,
            reasoning=None,
            needs_refinement=False,
            iteration=0
        )
        
        # Run graph
        result = await self.graph.ainvoke(initial_state, config)
        
        # Return formatted result
        return {
            "tags": result.get("validated_tags", []),
            "confidence_scores": result.get("confidence_scores", {}),
            "reasoning": result.get("reasoning", ""),
            "_iterations": result.get("iteration", 0)
        }
    
    async def astream_events(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None, version: str = "v1"):
        """Stream events from graph execution"""
        initial_state = TagState(
            text=input_data.get("text", ""),
            max_tags=input_data.get("max_tags", 5),
            tag_type=input_data.get("tag_type", "general"),
            raw_tags=None,
            validated_tags=None,
            confidence_scores=None,
            reasoning=None,
            needs_refinement=False,
            iteration=0
        )
        
        async for event in self.graph.astream_events(initial_state, config, version=version):
            yield event
    
    @staticmethod
    def get_structure() -> Dict[str, Any]:
        """Get the structure of this graph"""
        return {
            "nodes": [
                GraphNode(
                    id="generate_tags",
                    name="Generate Tags",
                    type="llm",
                    description="Generate initial tags from text using LLM",
                    inputs=["text", "max_tags", "tag_type"],
                    outputs=["raw_tags"]
                ).dict(),
                GraphNode(
                    id="validate_tags",
                    name="Validate Tags",
                    type="processing",
                    description="Validate and clean generated tags",
                    inputs=["raw_tags"],
                    outputs=["validated_tags", "needs_refinement"]
                ).dict(),
                GraphNode(
                    id="calculate_confidence",
                    name="Calculate Confidence",
                    type="analysis",
                    description="Calculate confidence scores for each tag",
                    inputs=["validated_tags", "text"],
                    outputs=["confidence_scores", "reasoning"]
                ).dict(),
                GraphNode(
                    id="refine_tags",
                    name="Refine Tags",
                    type="llm",
                    description="Generate additional tags if needed",
                    inputs=["validated_tags", "text"],
                    outputs=["raw_tags"]
                ).dict()
            ],
            "edges": [
                {"from": "generate_tags", "to": "validate_tags"},
                {"from": "validate_tags", "to": "calculate_confidence"},
                {"from": "calculate_confidence", "to": "refine_tags", "condition": "needs_refinement"},
                {"from": "calculate_confidence", "to": "END", "condition": "done"},
                {"from": "refine_tags", "to": "validate_tags"}
            ],
            "entry_point": "generate_tags",
            "description": "Graph for generating and validating tags from text with confidence scoring and refinement"
        }