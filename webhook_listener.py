from fastapi import FastAPI, Request
from datetime import datetime
import json
import uvicorn

app = FastAPI(
    title="Webhook Receiver",
    description="Simple webhook server for Contact Center notifications",
    version="1.0.0"
)

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


@app.post("/webhook")
async def receive_webhook(request: Request):
    """Receive and display webhook notifications"""
    try:
        payload = await request.json()
        
        # Format timestamp
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Determine event type and color
        event = payload.get("event", "unknown")
        
        # Print formatted output based on event type
        print(f"\n{Colors.BOLD}[{timestamp}] WEBHOOK RECEIVED{Colors.ENDC}")
        print("-" * 50)
        
        if event == "call_assigned":
            print(f"{Colors.GREEN}Event: {event}{Colors.ENDC}")
            print(f"  Call ID: {payload.get('call_id')}")
            print(f"  Agent ID: {payload.get('agent_id')}")
            print(f"  Agent Type: {payload.get('agent_type')}")
            print(f"  Call Type: {payload.get('call_type')}")
            print(f"  Wait Time: {payload.get('wait_time_seconds', 0):.2f}s")
            
        elif event == "call_queued":
            print(f"{Colors.YELLOW}Event: {event}{Colors.ENDC}")
            print(f"  Call ID: {payload.get('call_id')}")
            print(f"  Call Type: {payload.get('call_type')}")
            print(f"  Queue Position: {payload.get('queue_position')}")
            
        elif event == "call_completed":
            print(f"{Colors.BLUE}Event: {event}{Colors.ENDC}")
            print(f"  Call ID: {payload.get('call_id')}")
            print(f"  Agent ID: {payload.get('agent_id')}")
            print(f"  Result: {payload.get('result')}")
            print(f"  Duration: {payload.get('duration_seconds', 0):.1f}s")
            
        elif event == "agent_status_changed":
            print(f"{Colors.HEADER}Event: {event}{Colors.ENDC}")
            print(f"  Agent ID: {payload.get('agent_id')}")
            print(f"  Old Status: {payload.get('old_status')}")
            print(f"  New Status: {payload.get('new_status')}")
            
        elif event == "saturation_alert":
            print(f"{Colors.RED}Event: {event}{Colors.ENDC}")
            print(f"  Severity: {payload.get('severity')}")
            print(f"  Pending Calls: {payload.get('pending_calls')}")
            print(f"  Available Agents: {payload.get('available_agents')}")
        else:
            print(f"Event: {event}")
            print(f"Payload: {json.dumps(payload, indent=2)}")

        print("-" * 50)

        return {"status": "received", "timestamp": timestamp}

    except Exception as e:
        print(f"{Colors.RED}Error processing webhook: {e}{Colors.ENDC}")
        return {"status": "error", "message": str(e)}, 400


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Webhook Receiver",
        "status": "running",
        "endpoint": "/webhook",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health():
    """Health check for Docker"""
    return {"status": "healthy"}


if __name__ == "__main__":
    print(f"{Colors.BOLD}{Colors.GREEN}")
    print("=" * 60)
    print("WEBHOOK SERVER STARTED")
    print("=" * 60)
    print(f"{Colors.ENDC}")
    print("Listening for webhooks on: http://0.0.0.0:8001/webhook")
    print("Health check: http://0.0.0.0:8001/health")
    print("\nWaiting for notifications from Contact Center...")
    print("-" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8001)