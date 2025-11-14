#!/usr/bin/env python3
"""
Simple HTTP server for the Voice Bot Client Application

This serves the client app on http://localhost:3000
The client then connects to the API server via WebSocket.

Usage:
    python3 run_client.py [--port PORT]
"""

import http.server
import socketserver
import argparse
import os
import socket
import sys
import subprocess
import time

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()


class ReusableTCPServer(socketserver.TCPServer):
    """TCP Server with SO_REUSEADDR option to allow port reuse."""
    allow_reuse_address = True


def check_port_in_use(port):
    """Check if a port is already in use."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        sock.close()
        return False
    except OSError:
        return True


def find_process_using_port(port):
    """Find process ID using the specified port."""
    try:
        # Try lsof first (works on macOS/Linux)
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            return [int(pid) for pid in pids if pid.isdigit()]
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    
    return []


def kill_process_on_port(port):
    """Kill process using the specified port."""
    pids = find_process_using_port(port)
    if not pids:
        return False
    
    print(f"[Client Server] Found {len(pids)} process(es) using port {port}: {pids}")
    
    for pid in pids:
        try:
            print(f"[Client Server] Attempting to kill process {pid}...")
            subprocess.run(['kill', '-9', str(pid)], check=False, timeout=5)
            print(f"[Client Server] ✓ Killed process {pid}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"[Client Server] ⚠️  Could not kill process {pid}: {e}")
    
    # Wait a bit for port to be released
    time.sleep(1)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice Bot Client Server")
    parser.add_argument("--port", type=int, default=3000, help="Port to run on (default: 3000)")
    args = parser.parse_args()
    
    # Change to the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Use modular version if available, otherwise fall back
    modular_path = os.path.join(script_dir, 'index_modular.html')
    index_path = os.path.join(script_dir, 'index.html')
    
    if os.path.exists(modular_path):
        # Temporarily rename to index.html
        if os.path.exists(index_path) and not os.path.samefile(index_path, modular_path):
            os.rename(index_path, os.path.join(script_dir, 'index_backup.html'))
        if not os.path.exists(index_path):
            import shutil
            shutil.copy(modular_path, index_path)
        print("✅ Using modular Silero VAD version (HTML + separate JS modules)")
    
    print("\n" + "="*60)
    print("🎙️  Voice Bot Client Application")
    print("="*60)
    print(f"Client URL: http://localhost:{args.port}")
    print(f"File: index.html")
    print("="*60)
    print("\n📝 Instructions:")
    print("   1. Ensure API server is running (python server.py)")
    print(f"   2. Open: http://localhost:{args.port}")
    print("   3. Click 'Connect' to connect to API server")
    print("   4. Click 'Start Listening' and speak!")
    print("="*60 + "\n")
    
    # Check if port is in use
    if check_port_in_use(args.port):
        print(f"⚠️  Port {args.port} is already in use.")
        print(f"[Client Server] Attempting to free port {args.port}...")
        
        # Try to kill process using the port
        if kill_process_on_port(args.port):
            print(f"[Client Server] Waiting for port {args.port} to be released...")
            time.sleep(2)
        
        # Check again
        if check_port_in_use(args.port):
            print(f"\n❌ ERROR: Port {args.port} is still in use.")
            print(f"\n💡 Solutions:")
            print(f"   1. Kill the process using port {args.port} manually:")
            print(f"      lsof -ti:{args.port} | xargs kill -9")
            print(f"   2. Use a different port:")
            print(f"      python3 run_client.py --port 3001")
            print(f"   3. Wait a few seconds and try again (port may be in TIME_WAIT state)")
            sys.exit(1)
        else:
            print(f"✅ Port {args.port} is now available.")
    
    # Try to start the server with SO_REUSEADDR
    try:
        print(f"[Client Server] Starting server on port {args.port}...")
        with ReusableTCPServer(("", args.port), MyHTTPRequestHandler) as httpd:
            print(f"✅ Client server started successfully!")
            print(f"🌐 Open http://localhost:{args.port} in your browser\n")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n\n[Client Server] Shutting down...")
                httpd.shutdown()
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"\n❌ ERROR: Port {args.port} is already in use.")
            print(f"\n💡 Solutions:")
            print(f"   1. Kill the process using port {args.port}:")
            print(f"      lsof -ti:{args.port} | xargs kill -9")
            print(f"   2. Use a different port:")
            print(f"      python3 run_client.py --port 3001")
            print(f"   3. Wait a few seconds and try again")
            sys.exit(1)
        else:
            print(f"\n❌ ERROR: Failed to start server: {e}")
            sys.exit(1)

