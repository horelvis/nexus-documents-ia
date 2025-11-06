"""Simple test workflow for Temporalio service startup"""
from dataclasses import dataclass
from temporalio import workflow


@dataclass 
class SimpleWorkflowInput:
    message: str


@dataclass
class SimpleWorkflowResult:
    result: str


@workflow.defn
class SimpleWorkflow:
    """Simple test workflow"""
    
    @workflow.run
    async def run(self, input_data: SimpleWorkflowInput) -> SimpleWorkflowResult:
        """Execute simple workflow"""
        return SimpleWorkflowResult(result=f"Processed: {input_data.message}")