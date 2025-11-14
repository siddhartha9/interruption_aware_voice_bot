"""
AI Agent Module using LangGraph and Groq with Tool Calling.

This module manages the conversational AI agent using LangGraph for stateful
conversation management and Groq for ultra-fast LLM inference.
Includes tool calling capabilities for extended functionality.
Supports async tools with cancellation via ActiveToolRegistry.
"""

import asyncio
import os
from typing import List, Dict, AsyncGenerator, Optional, TypedDict, Annotated, Literal
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# Import tools from separate module
from .tools import TOOLS, SYNC_TOOLS, ASYNC_TOOLS


# ============================================================================
# AGENT STATE
# ============================================================================

class ConversationState(TypedDict):
    """State for the conversation graph."""
    messages: Annotated[list, add_messages]


# ============================================================================
# AI AGENT CLASS
# ============================================================================

class AIAgent:
    """
    AI Agent powered by LangGraph and Groq with tool calling support.
    
    This module manages stateful conversations with streaming support and
    can call tools to extend its capabilities beyond text generation.
    """
    
    def __init__(
        self, 
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.7,
        system_prompt: str = None,
        enable_tools: bool = True
    ):
        """
        Initialize the AI agent with Groq and optional tool calling.
        
        Args:
            api_key: Groq API key
            model: Groq model identifier (default: llama-3.3-70b-versatile)
            temperature: Generation temperature (0.0-1.0)
            system_prompt: Optional system instructions
            enable_tools: Whether to enable tool calling (default: True)
        """
        self.model_name = model
        self.temperature = temperature
        self.is_cancelled = False
        self.current_task: Optional[asyncio.Task] = None
        self.enable_tools = enable_tools
        self.api_key = api_key  # Store API key for fallback
        
        # Default system prompt if none provided
        self.system_prompt = system_prompt or (
            "You are a helpful, friendly AI voice assistant. "
            "Keep your responses concise and conversational, as they will be spoken aloud. "
            "Aim for 2-3 sentences unless more detail is explicitly requested. "
            "Only use tools when absolutely necessary. Prefer to answer directly when possible."
        )
        
        # Initialize Groq LLM
        try:
            if not api_key or len(api_key) < 10:
                raise ValueError(f"Invalid Groq API key (length: {len(api_key) if api_key else 0})")
            
            print(f"[AI Agent] Using API key: {api_key[:10]}...{api_key[-4:]} (length: {len(api_key)})")
            
            # Create LLM with tool binding if enabled
            self.llm = ChatGroq(
                model=model,
                groq_api_key=api_key,
                temperature=temperature,
                streaming=True,
                max_retries=3,
                timeout=30.0,
            )
            
            if self.enable_tools:
                self.llm_with_tools = self.llm.bind_tools(TOOLS)
                print(f"[AI Agent] ✓ Initialized Groq ({model}) with {len(TOOLS)} tools")
                print(f"[AI Agent] 🛠️ Available tools: {', '.join([t.name for t in TOOLS])}")
            else:
                self.llm_with_tools = self.llm
                print(f"[AI Agent] ✓ Initialized Groq ({model}) without tools")
            
            print(f"[AI Agent] ⚡ Ultra-fast inference: 500+ tokens/second!")
        except Exception as e:
            print(f"[AI Agent] ✗ Failed to initialize Groq: {e}")
            raise
        
        # Build LangGraph workflow
        self._build_graph()
    
    def _build_graph(self):
        """Build the LangGraph conversation workflow with tool calling."""
        workflow = StateGraph(ConversationState)
        
        # Add agent node
        workflow.add_node("agent", self._agent_node)
        
        if self.enable_tools:
            # Add tool node
            tool_node = ToolNode(TOOLS)
            workflow.add_node("tools", tool_node)
            
            # Add conditional edge: agent -> tools or END
            workflow.add_conditional_edges(
                "agent",
                self._should_continue,
                {
                    "tools": "tools",
                    "end": END,
                }
            )
            
            # Tools always go back to agent
            workflow.add_edge("tools", "agent")
        else:
            # No tools - agent goes directly to END
            workflow.add_edge("agent", END)
        
        # Set entry point
        workflow.set_entry_point("agent")
        
        # Compile the graph
        self.graph = workflow.compile()
        tool_status = f"with tool calling" if self.enable_tools else "without tools"
        print(f"[AI Agent] LangGraph workflow compiled ({tool_status})")
    
    def _should_continue(self, state: ConversationState) -> Literal["tools", "end"]:
        """
        Determine whether to call tools or end the conversation.
        
        Args:
            state: Current conversation state
            
        Returns:
            "tools" if the agent wants to call tools, "end" otherwise
        """
        messages = state["messages"]
        last_message = messages[-1]
        
        # If the last message has tool calls, route to tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            print(f"[AI Agent] 🛠️ Tool calls requested: {len(last_message.tool_calls)}")
            return "tools"
        
        # Otherwise, end the conversation
        return "end"
    
    async def _agent_node(self, state: ConversationState) -> ConversationState:
        """
        Agent processing node.
        
        Args:
            state: Current conversation state
            
        Returns:
            Updated state with AI response
        """
        messages = state["messages"]
        
        # Prepend system message if we have one
        if self.system_prompt:
            messages_with_system = [SystemMessage(content=self.system_prompt)] + messages
        else:
            messages_with_system = messages
        
        # Call LLM (with tools if enabled)
        try:
            response = await self.llm_with_tools.ainvoke(messages_with_system)
            return {"messages": [response]}
        except Exception as e:
            # If tool calling fails, try without tools
            error_msg = str(e)
            print(f"[AI Agent] Error in agent node: {error_msg}")
            
            # If it's a tool calling error and tools are enabled, retry without tools
            if "Failed to call a function" in error_msg and self.enable_tools:
                print("[AI Agent] ⚠️ Tool calling failed, retrying without tools...")
                try:
                    # Create a temporary LLM without tools for this request
                    fallback_llm = ChatGroq(
                        model=self.model_name,
                        groq_api_key=self.api_key,
                        temperature=self.temperature,
                        streaming=True,
                        max_retries=3,
                        timeout=30.0,
                    )
                    response = await fallback_llm.ainvoke(messages_with_system)
                    print("[AI Agent] ✓ Fallback (no tools) succeeded")
                    return {"messages": [response]}
                except Exception as retry_error:
                    print(f"[AI Agent] Error in fallback (no tools): {retry_error}")
                    import traceback
                    traceback.print_exc()
                    # Return an error message
                    from langchain_core.messages import AIMessage
                    error_response = AIMessage(
                        content="I apologize, but I'm experiencing technical difficulties. Please try again."
                    )
                    return {"messages": [error_response]}
            else:
                # Other errors - return error message
                from langchain_core.messages import AIMessage
                error_response = AIMessage(
                    content="I apologize, but I'm experiencing technical difficulties. Please try again."
                )
                return {"messages": [error_response]}
    
    async def generate_response(
        self, 
        chat_history: List[Dict[str, str]]
    ) -> AsyncGenerator[Optional[str], None]:
        """
        Generate a streaming response based on chat history.
        
        This method handles both direct text responses and tool-calling flows.
        
        Args:
            chat_history: List of messages with 'role' and 'content' keys
                         (format: [{"role": "user"|"assistant", "content": "..."}])
            
        Yields:
            Text chunks as they are generated, None to signal end of stream
        """
        self.is_cancelled = False
        
        try:
            print(f"[AI Agent] Generating response for {len(chat_history)} messages")
            
            # Convert chat history to LangChain message format
            langchain_messages = []
            for msg in chat_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                if role == "user":
                    langchain_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    langchain_messages.append(AIMessage(content=content))
            
            # Stream response using LangGraph
            # Note: Tool calls will be handled automatically by the graph
            async for event in self.graph.astream(
                {"messages": langchain_messages},
                config={"configurable": {"thread_id": "1"}},
                stream_mode="values"
            ):
                if self.is_cancelled:
                    print("[AI Agent] Generation cancelled")
                    break
                
                # Get the last message from the event
                if "messages" in event and len(event["messages"]) > 0:
                    last_message = event["messages"][-1]
                    
                    # Only yield content from AIMessage (not ToolMessage)
                    if isinstance(last_message, AIMessage) and last_message.content:
                        # Check if this is a new message we haven't yielded yet
                        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
                            yield last_message.content
            
            # Signal end of stream
            yield None
            
        except asyncio.CancelledError:
            print("[AI Agent] Generation task cancelled")
            raise
        except Exception as e:
            print(f"[AI Agent] Error during generation: {e}")
            import traceback
            traceback.print_exc()
            yield None
    
    def cancel(self):
        """
        Cancel the current generation task.
        
        This will stop the LLM stream and any ongoing tool calls.
        """
        print("[AI Agent] Cancellation requested")
        self.is_cancelled = True
        
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
    
    def set_system_prompt(self, system_prompt: str):
        """
        Set or update the system prompt for the agent.
        
        Args:
            system_prompt: The system instructions for the AI
        """
        self.system_prompt = system_prompt
        print(f"[AI Agent] System prompt updated: {system_prompt[:50]}...")
    
    def reset_conversation(self):
        """Reset the agent state for a new conversation."""
        self.cancel()
        print("[AI Agent] Conversation state reset")

    def get_available_tools(self) -> List[str]:
        """
        Get list of available tool names.
        
        Returns:
            List of tool names
        """
        return [tool.name for tool in TOOLS]


# ============================================================================
# TOOL EXECUTOR (Legacy - kept for backwards compatibility)
# ============================================================================

class ToolExecutor:
    """
    Legacy tool executor for backwards compatibility.
    
    Note: Tool execution is now handled automatically by LangGraph's ToolNode.
    This class is kept for any code that might still reference it.
    """
    
    def __init__(self):
        """Initialize the tool executor."""
        self.pending_jobs: List[asyncio.Task] = []
        print("[Tool Executor] Initialized (legacy mode)")
    
    async def execute_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """
        Execute a tool/function call.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        print(f"[Tool Executor] Executing {tool_name} with args: {arguments}")
        
        # Map to actual tools
        tool_map = {tool.name: tool for tool in TOOLS}
        
        if tool_name in tool_map:
            tool_func = tool_map[tool_name]
            result = await asyncio.to_thread(tool_func.invoke, arguments)
            return {"status": "success", "result": result}
        else:
            return {"status": "error", "result": f"Tool '{tool_name}' not found"}
    
    def cancel_all_pending_jobs(self):
        """Cancel all pending tool execution jobs."""
        print(f"[Tool Executor] Cancelling {len(self.pending_jobs)} pending jobs")
        for job in self.pending_jobs:
            if not job.done():
                job.cancel()
        self.pending_jobs.clear()
