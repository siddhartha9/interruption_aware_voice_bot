#!/usr/bin/env python3
"""
Voice Bot Orchestrator - WebSocket API Server

This is a pure API server that handles WebSocket connections for voice bot conversations.
The client application should be hosted separately.

Usage:
    python server.py [--host HOST] [--port PORT]
    
Example:
    python server.py --host 0.0.0.0 --port 8000
"""

import asyncio
import argparse
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from src.server.orchestrator import ConnectionOrchestrator

# Create FastAPI app
app = FastAPI(
    title="Voice Bot Orchestrator API",
    description="WebSocket API for conversational voice bot with interruption handling",
    version="2.2"
)

# Add CORS middleware to allow client connections from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain: ["https://yourdomain.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def get_root():
    """Root endpoint with API information."""
    return {
        "name": "Voice Bot Orchestrator API",
        "version": "2.2",
        "status": "running",
        "endpoints": {
            "websocket": "ws://127.0.0.1:8000/ws",
            "health": "/health",
            "docs": "/docs"
        },
        "client_info": {
            "message": "This is an API-only server. Deploy your client application separately.",
            "client_file": "client.html (deploy to Netlify, Vercel, or any static hosting)"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    # Check if API keys are configured
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    return {
        "status": "healthy",
        "service": "voice-bot-orchestrator",
        "version": "2.4",
        "deepgram_configured": bool(deepgram_key and len(deepgram_key) > 0),
        "groq_configured": bool(groq_key and len(groq_key) > 0),
        "groq_model": groq_model if groq_key else None,
        "performance": "⚡ Ultra-fast with Groq (500+ tokens/sec)"
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for voice bot communication.
    
    Each connection gets its own isolated ConnectionOrchestrator instance.
    
    Protocol:
        Client sends:
            - {"type": "speech_start"}
            - {"type": "speech_end", "audio": "<base64-encoded-audio>"}
        
        Server sends:
            - {"event": "connected", "message": "..."}
            - {"event": "audio_chunk", "audio": "<base64-encoded-audio>"}
            - {"event": "playback_pause"}
            - {"event": "playback_resume"}
            - {"event": "conversation_turn", "user": "...", "assistant": "..."}
    """
    await websocket.accept()
    
    # Get API keys from environment
    deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")
    if not deepgram_api_key:
        print("[Server] ERROR: DEEPGRAM_API_KEY not found in environment!")
        await websocket.send_json({
            "event": "error",
            "message": "Server configuration error: DEEPGRAM_API_KEY not set"
        })
        await websocket.close()
        return
    
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        print("[Server] ERROR: GROQ_API_KEY not found in environment!")
        await websocket.send_json({
            "event": "error",
            "message": "Server configuration error: GROQ_API_KEY not set"
        })
        await websocket.close()
        return
    
    # Debug: Log API key info
    print(f"[Server] Loaded Groq API key: {groq_api_key[:10]}...{groq_api_key[-4:]} (length: {len(groq_api_key)})")
    
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    print(f"[Server] Using Groq model: {groq_model} ⚡")
    
    # Create isolated orchestrator for this connection
    orchestrator = ConnectionOrchestrator(
        websocket, 
        deepgram_api_key,
        groq_api_key,
        groq_model
    )
    
    try:
        print(f"\n{'='*60}")
        print(f"[Server] New client connected! Session: {orchestrator.session_id}")
        print(f"{'='*60}\n")
        
        # Start background workers for this connection
        await orchestrator.start_workers()
        
        # Send welcome message
        await websocket.send_json({
            "event": "connected",
            "message": f"Connected to Voice Bot Orchestrator (Session: {orchestrator.session_id})",
            "session_id": orchestrator.session_id
        })
        
        # Main message loop
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            event_type = data.get('type')
            print(f"[Server] Received event: {event_type}")
            
            # Route event to orchestrator
            await orchestrator.handle_client_event(data)
            
    except WebSocketDisconnect:
        print(f"\n[Server] Client disconnected: {orchestrator.session_id}")
        
    except Exception as e:
        print(f"\n[Server] ERROR in WebSocket connection: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Clean up orchestrator resources
        print(f"[Server] Cleaning up session: {orchestrator.session_id}")
        await orchestrator.cleanup()
        print(f"[Server] Session cleaned up: {orchestrator.session_id}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice Bot Orchestrator Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("🎙️  Voice Bot Orchestrator API Server")
    print("="*60)
    print(f"Version: 2.2")
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"WebSocket URL: ws://{args.host}:{args.port}/ws")
    print(f"API Docs: http://{args.host}:{args.port}/docs")
    print("="*60)
    print("\n⚠️  This is an API-only server.")
    print("   Deploy your client application separately!")
    print(f"   Client file: client.html\n")
    print("="*60 + "\n")
    
    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )
