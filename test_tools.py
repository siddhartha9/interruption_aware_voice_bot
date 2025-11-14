"""
Quick test script for tool calling functionality.
"""
import asyncio
import os
from dotenv import load_dotenv
from src.server.ai_agent import AIAgent

load_dotenv()

async def test_tools():
    """Test each tool with the AI agent."""
    
    # Get API key
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("❌ GROQ_API_KEY not found in .env")
        return
    
    # Initialize agent
    print("Initializing AI Agent with tools...")
    agent = AIAgent(api_key=api_key, enable_tools=True)
    print(f"\n✓ Agent initialized with tools: {agent.get_available_tools()}\n")
    
    # Test cases
    test_queries = [
        "What time is it?",
        "What's the weather in Paris?",
        "Calculate 15 times 7",
        "Tell me about Python",
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"USER: {query}")
        print(f"{'='*60}")
        
        chat_history = [{"role": "user", "content": query}]
        
        print("AGENT: ", end="", flush=True)
        async for chunk in agent.generate_response(chat_history):
            if chunk:
                print(chunk, end="", flush=True)
        print("\n")

if __name__ == "__main__":
    asyncio.run(test_tools())
