#!/bin/bash
#
# Generate Real Audio Samples for Load Testing
#
# This script uses macOS 'say' command to generate real speech audio
# that Deepgram can actually transcribe.
#

set -e

AUDIO_DIR="$(cd "$(dirname "$0")" && pwd)/audio_samples"

echo "🎤 Generating real speech audio samples..."
echo "📁 Output directory: $AUDIO_DIR"
echo ""

# Create directory if it doesn't exist
mkdir -p "$AUDIO_DIR"

# Generate different duration samples for different test scenarios

# 1. Normal queries (2 seconds)
echo "Generating 2-second queries..."
say "What is my account balance?" -o "$AUDIO_DIR/query_2s_balance.wav" --data-format=LEI16@16000 --channels=1
say "Tell me about my recent transactions" -o "$AUDIO_DIR/query_2s_transactions.wav" --data-format=LEI16@16000 --channels=1
say "How can I help you today?" -o "$AUDIO_DIR/query_2s_help.wav" --data-format=LEI16@16000 --channels=1
say "What services do you offer?" -o "$AUDIO_DIR/query_2s_services.wav" --data-format=LEI16@16000 --channels=1

# 2. Tool call queries (3 seconds)
echo "Generating 3-second tool call queries..."
say "Can you please email my bank statement to me?" -o "$AUDIO_DIR/query_3s_email.wav" --data-format=LEI16@16000 --channels=1
say "I would like to check my account balance right now" -o "$AUDIO_DIR/query_3s_check_balance.wav" --data-format=LEI16@16000 --channels=1

# 3. Short interruption queries (1.5 seconds)
echo "Generating 1.5-second interruption queries..."
say "Wait, tell me something else" -o "$AUDIO_DIR/query_1_5s_interrupt.wav" --data-format=LEI16@16000 --channels=1
say "Actually, I have another question" -o "$AUDIO_DIR/query_1_5s_another.wav" --data-format=LEI16@16000 --channels=1

# 4. False alarm / noise (0.3 seconds)
echo "Generating 0.3-second false alarm audio..."
say "Mhmm" -o "$AUDIO_DIR/noise_0_3s_mhmm.wav" --data-format=LEI16@16000 --channels=1
say "Uh" -o "$AUDIO_DIR/noise_0_3s_uh.wav" --data-format=LEI16@16000 --channels=1

echo ""
echo "✅ Audio generation complete!"
echo ""
echo "Generated files:"
ls -lh "$AUDIO_DIR"/*.wav | awk '{print "  " $9 " (" $5 ")"}'
echo ""
echo "🎯 You can now run the load test with real audio:"
echo "   cd /Users/suman/Documents/voice_bot"
echo "   python3 src/load_test/load_test.py --concurrency 10 --requests 5"
echo ""

