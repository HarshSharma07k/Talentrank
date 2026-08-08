import time
import requests
import numpy as np


def test_latency():
    url = "http://localhost:8000/match"
    payload = {"resume_text": "Experienced machine learning engineer skilled in Python, Docker, and AWS."}

    # Warm-up request (forces models to load into memory if you didn't do it at startup)
    print("Sending warm-up request...")
    try:
        requests.post(url, json=payload)
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect. Is your uvicorn server running on localhost:8000?")
        return

    latencies = []
    num_requests = 50

    print(f"Firing {num_requests} requests to measure latency...")

    for i in range(num_requests):
        start_time = time.time()
        response = requests.post(url, json=payload)
        end_time = time.time()

        if response.status_code == 200:
            latencies.append((end_time - start_time) * 1000)  # Convert to ms
        else:
            print(f"❌ Request {i + 1} failed with status {response.status_code}")

    if not latencies:
        return

    p50 = np.percentile(latencies, 50)
    p95 = np.percentile(latencies, 95)

    print("\n✅ Latency Test Complete")
    print("=== API PERFORMANCE ===")
    print(f"p50 Latency: {p50:.2f} ms  <-- (Put this on your resume)")
    print(f"p95 Latency: {p95:.2f} ms")
    print("=======================")


if __name__ == "__main__":
    test_latency()
