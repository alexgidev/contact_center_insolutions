import asyncio
import httpx
import random
import statistics
from collections import defaultdict
import time


API_URL = "http://localhost:8000"
NUM_AGENTS = 25
NUM_CALLS = 1000
CALLS_PER_SECOND = 3
CALL_DURATION = 10


CONVERSION_MATRIX = {
    (1, 1): 0.30, (1, 2): 0.20, (1, 3): 0.10, (1, 4): 0.05,
    (2, 1): 0.20, (2, 2): 0.15, (2, 3): 0.07, (2, 4): 0.04,
    (3, 1): 0.15, (3, 2): 0.12, (3, 3): 0.06, (3, 4): 0.03,
    (4, 1): 0.12, (4, 2): 0.10, (4, 3): 0.04, (4, 4): 0.02,
}


response_times = []
call_results = defaultdict(lambda: {"OK": 0, "KO": 0, "total": 0})
calls_processed = 0
summary_interval = 50


async def create_agents(client: httpx.AsyncClient):
    """Create agents with balanced types via API"""
    print(f"Creating {NUM_AGENTS} agents (4 of each type)...")
    for agent_id in range(NUM_AGENTS):
        agent_type = random.randint(1, 4)
        agent_data = {
            "reference_code": 1000 + agent_id,
            "agent_type": agent_type,
            "tenant_id": 1
        }
        try:
            response = await client.post(
                f"{API_URL}/agent/new",
                json=agent_data
            )
            if response.status_code == 200:
                data = response.json()
                actual_agent_id = data['agent_id']
                print(f"Created agent {actual_agent_id} (type {agent_type})")
            else:
                print(f"Error creating agent: {response.status_code}")
        except Exception as e:
            print(f"Error: {e}")
    print(f"Created {NUM_AGENTS} agents successfully\n")


async def handle_call(
    client: httpx.AsyncClient,
    call_number: int
):
    """Send a call, simulate duration, compute OK/KO,
    and update metrics via API"""
    global calls_processed
    call_type = ((call_number - 1) % 4) + 1
    call_data = {"call_type": call_type, "tenant_id": 1}

    start_time = time.perf_counter()
    try:
        # 1. Create call in API
        response = await client.post(f"{API_URL}/call/new", json=call_data)
        response_time_ms = (time.perf_counter() - start_time) * 1000
        response_times.append(response_time_ms)

        if response.status_code != 200:
            print(
                f"Call {call_number:3d} ERROR {response.status_code} | "
                f"{response_time_ms:6.2f}ms"
            )
            return

        data = response.json()
        call_id = data.get('call_id')
        status = data.get("status", "unknown")
        agent_id = data.get("agent_id") # Can be None if queued

        if status == "queued":
            queue_pos = data.get("queue_position", "?")
            print(
                f"Call {call_number:3d} queued | position {queue_pos} | {response_time_ms:6.2f}ms"
            )
            # The API is handling the queue. We just need to wait for the call to be processed.
            # We'll wait for the call duration plus an extra delay for queue time.
            # This is an approximation since the simulator doesn't know the real queue time.
            await asyncio.sleep(CALL_DURATION + 2) # Wait for call duration + buffer

        elif status == "assigned":
            if calls_processed < 10:
                print(
                    f"Call {call_number:3d} | Type {call_type} | "
                    f"Assigned agent {agent_id:2d} | "
                    f"{response_time_ms:6.2f}ms | Processing..."
                )
            # Simulate call duration
            await asyncio.sleep(CALL_DURATION)
        else:
            print(f"Call {call_number:3d} received unknown status: {status}")
            return


        # 2. Determine result and finish the call
        # This part runs for both queued and assigned calls after waiting.
        agent_type = random.randint(1, 4)
        probability = CONVERSION_MATRIX.get((agent_type, call_type), 0.1)
        result = "OK" if random.random() < probability else "KO"

        # Finish call in API
        finish_response = await client.post(f"{API_URL}/call/finished/{call_id}", json={"result": result})
        if finish_response.status_code != 200:
            # It might fail if the call was never assigned (e.g., simulation ends too early)
            print(f"Call {call_number:3d} ERROR finishing call {call_id}: {finish_response.status_code} - {finish_response.text}")
            return

        # 3. Update local metrics
        key = f"Agent{agent_type}_Call{call_type}"
        call_results[key]["total"] += 1
        call_results[key][result] += 1

        calls_processed += 1
        if calls_processed <= 10 or calls_processed % summary_interval == 0:
            ok_total = sum(d["OK"] for d in call_results.values())
            total = sum(d["total"] for d in call_results.values())
            ok_percentage = (ok_total / total) * 100 if total > 0 else 0
            avg_resp = sum(response_times)/len(response_times) if response_times else 0
            print(f"Processed {calls_processed}/{NUM_CALLS} calls | OK: {ok_percentage:.1f}% | Avg response: {avg_resp:.2f}ms")

    except Exception as e:
        print(f"Call {call_number:3d} Exception: {e}")


async def run_simulation():
    print("=" * 80)
    print("REALISTIC ASYNC CALL CENTER SIMULATOR")
    print("=" * 80)
    print(f"Agents={NUM_AGENTS}, Calls={NUM_CALLS}, Rate={CALLS_PER_SECOND}/sec, Duration={CALL_DURATION}s")
    print("=" * 80)

    async with httpx.AsyncClient() as client:
        # 1️⃣ Create agents
        await create_agents(client)

        # 2️⃣ Send calls concurrently
        print(f"Sending {NUM_CALLS} calls...")
        tasks = []
        for i in range(1, NUM_CALLS + 1):
            tasks.append(asyncio.create_task(handle_call(client, i)))
            await asyncio.sleep(1.0 / CALLS_PER_SECOND)

        await asyncio.gather(*tasks)  # Wait for all tasks to complete

    show_statistics()


def show_statistics():
    print("\nRESPONSE TIME STATISTICS")
    print("=" * 80)
    if response_times:
        avg_time = statistics.mean(response_times)
        min_time = min(response_times)
        max_time = max(response_times)
        median_time = statistics.median(response_times)
        under_100ms = sum(1 for t in response_times if t < 100)
        percentage_under_100 = (under_100ms / len(response_times)) * 100

        print(f"Total calls: {len(response_times)} | Avg: {avg_time:.2f}ms | Min: {min_time:.2f}ms | Max: {max_time:.2f}ms | Median: {median_time:.2f}ms | <100ms: {percentage_under_100:.1f}%")

    print("\nCONVERSION RATE VALIDATION")
    print("=" * 80)
    print(f"{'Combination':>20} {'Total':>8} {'OK':>8} {'KO':>8} {'OK Rate':>12} {'Expected':>12} {'Diff':>8}")
    for agent_type in range(1, 5):
        for call_type in range(1, 5):
            key = f"Agent{agent_type}_Call{call_type}"
            data = call_results[key]
            if data["total"] > 0:
                actual_rate = data["OK"] / data["total"]
                expected_rate = CONVERSION_MATRIX.get((agent_type, call_type), 0)
                diff = abs(actual_rate - expected_rate)
                print(f"{key:>20} {data['total']:>8} {data['OK']:>8} {data['KO']:>8} "
                      f"{actual_rate*100:>11.1f}% {expected_rate*100:>11.1f}% {diff*100:>8.1f}%")


if __name__ == "__main__":
    async def main():
        print("Checking API connection...")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{API_URL}/health")
                if response.status_code == 200:
                    print("API connected and running\n")
                    start_total = time.time()
                    await run_simulation()
                    total_time = time.time() - start_total
                    print(f"\nTotal simulation time: {total_time:.2f} seconds")
                else:
                    print("API is not responding correctly")
                    print(f"   Status: {response.status_code}")
            except Exception as e:
                print(f"Cannot connect to API at {API_URL}")
                print(f"   Error: {e}")
                print("\nMake sure the API is running: python main.py")

    asyncio.run(main())
