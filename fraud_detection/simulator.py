"""Transaction simulator - generates realistic transaction streams with injected fraud."""

import json
import time
import random
import logging
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


MERCHANTS = {
    "grocery": ["Whole Foods", "Trader Joes", "Kroger", "Safeway", "Costco"],
    "gas": ["Shell", "Chevron", "BP", "ExxonMobil"],
    "restaurant": ["McDonalds", "Starbucks", "Chipotle", "Local Bistro"],
    "retail": ["Target", "Walmart", "Best Buy", "Amazon"],
    "online": ["Amazon.com", "eBay", "Shopify Store", "Etsy"],
    "travel": ["United Airlines", "Marriott", "Hilton", "Hertz"],
    "entertainment": ["Netflix", "Spotify", "AMC Theaters", "Steam"],
    "electronics": ["Apple Store", "Samsung", "NewEgg"],
    "jewelry": ["Tiffany", "Kay Jewelers", "Blue Nile"],
}


def generate_legit_transaction(customer_id: str) -> dict:
    category = random.choice(["grocery", "gas", "restaurant", "retail", "online", "entertainment"])
    return {
        "transaction_id": f"TXN-{random.randint(10000000, 99999999)}",
        "customer_id": customer_id,
        "amount": round(random.lognormvariate(3.0, 1.0), 2),
        "merchant_category": category,
        "merchant_name": random.choice(MERCHANTS.get(category, ["Unknown"])),
        "card_present": random.choices([0, 1], weights=[25, 75])[0],
        "international": random.choices([0, 1], weights=[95, 5])[0],
        "distance_from_home": round(random.expovariate(1/15), 1),
        "distance_from_last_txn": round(random.expovariate(1/8), 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def generate_fraud_transaction(customer_id: str) -> dict:
    category = random.choice(["online", "electronics", "jewelry", "travel", "wire_transfer"])
    return {
        "transaction_id": f"TXN-{random.randint(10000000, 99999999)}",
        "customer_id": customer_id,
        "amount": round(random.lognormvariate(5.5, 1.5), 2),
        "merchant_category": category,
        "merchant_name": random.choice(MERCHANTS.get(category, ["Suspicious Vendor"])),
        "card_present": random.choices([0, 1], weights=[70, 30])[0],
        "international": random.choices([0, 1], weights=[50, 50])[0],
        "distance_from_home": round(random.expovariate(1/100), 1),
        "distance_from_last_txn": round(random.expovariate(1/80), 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_simulator(stream_name: str, region: str = "us-east-1",
                  tps: float = 5.0, fraud_rate: float = 0.03,
                  duration_seconds: int = 300):
    """
    Run transaction simulator, sending to Kinesis.

    Parameters
    ----------
    stream_name : str
        Kinesis stream name.
    tps : float
        Transactions per second.
    fraud_rate : float
        Fraction of transactions that are fraudulent.
    duration_seconds : int
        How long to run (0 = infinite).
    """
    kinesis = boto3.client("kinesis", region_name=region)
    customers = [f"CUST-{i:04d}" for i in range(100)]

    count = 0
    frauds = 0
    start = time.time()

    logger.info(f"Starting simulator: {tps} TPS, {fraud_rate:.1%} fraud rate, stream={stream_name}")

    try:
        while True:
            elapsed = time.time() - start
            if duration_seconds > 0 and elapsed >= duration_seconds:
                break

            customer = random.choice(customers)
            is_fraud = random.random() < fraud_rate
            txn = generate_fraud_transaction(customer) if is_fraud else generate_legit_transaction(customer)
            txn["_is_fraud_injected"] = is_fraud

            kinesis.put_record(
                StreamName=stream_name,
                Data=json.dumps(txn).encode("utf-8"),
                PartitionKey=customer,
            )

            count += 1
            if is_fraud:
                frauds += 1

            if count % 100 == 0:
                logger.info(f"Sent {count} transactions ({frauds} fraud) in {elapsed:.1f}s")

            time.sleep(1 / tps)

    except KeyboardInterrupt:
        pass

    logger.info(f"Simulator stopped: {count} transactions, {frauds} fraudulent ({frauds/max(count,1):.1%})")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stream", default="fraud-detection-stream")
    parser.add_argument("--tps", type=float, default=5.0)
    parser.add_argument("--fraud-rate", type=float, default=0.03)
    parser.add_argument("--duration", type=int, default=300)
    args = parser.parse_args()
    run_simulator(args.stream, tps=args.tps, fraud_rate=args.fraud_rate, duration_seconds=args.duration)
