#!/bin/bash
# Restart script - kills old processes and starts fresh

echo "🛑 Stopping old processes..."

# Kill server (port 8000)
lsof -ti:8000 | xargs kill -9 2>/dev/null && echo "  ✓ Port 8000 freed" || echo "  • Port 8000 was not in use"

# Kill client (port 3000)
lsof -ti:3000 | xargs kill -9 2>/dev/null && echo "  ✓ Port 3000 freed" || echo "  • Port 3000 was not in use"

sleep 1

echo ""
echo "🚀 Starting server and client..."
echo ""

# Start in current terminal (foreground mode)
cd "$(dirname "$0")"
source venv/bin/activate

# Start server in background
echo "Starting server on port 8000..."
python server.py &
SERVER_PID=$!

sleep 2

# Start client in background
echo "Starting client on port 3000..."
cd client_app
python run_client.py &
CLIENT_PID=$!

cd ..

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ✅ Server & Client Started!                                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  📡 Server:  http://127.0.0.1:8000"
echo "  🌐 Client:  http://localhost:3000"
echo ""
echo "  Server PID: $SERVER_PID"
echo "  Client PID: $CLIENT_PID"
echo ""
echo "To stop:"
echo "  kill $SERVER_PID $CLIENT_PID"
echo "  OR press Ctrl+C twice"
echo ""
echo "Logs will appear below..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Wait for both processes
wait

