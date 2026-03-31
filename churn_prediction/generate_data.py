"""Generate realistic synthetic telco churn dataset."""

import numpy as np
import pandas as pd


def generate_churn_data(n_customers: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)

    customer_id = [f"CUST-{i:06d}" for i in range(n_customers)]
    gender = rng.choice(["Male", "Female"], n_customers)
    senior_citizen = rng.choice([0, 1], n_customers, p=[0.84, 0.16])
    partner = rng.choice(["Yes", "No"], n_customers, p=[0.48, 0.52])
    dependents = rng.choice(["Yes", "No"], n_customers, p=[0.30, 0.70])
    tenure = rng.exponential(scale=32, size=n_customers).clip(1, 72).astype(int)

    contract = rng.choice(["Month-to-month", "One year", "Two year"],
                          n_customers, p=[0.55, 0.21, 0.24])
    payment_method = rng.choice(
        ["Electronic check", "Mailed check", "Bank transfer", "Credit card"],
        n_customers, p=[0.34, 0.23, 0.22, 0.21])
    paperless = rng.choice(["Yes", "No"], n_customers, p=[0.60, 0.40])

    phone_service = rng.choice(["Yes", "No"], n_customers, p=[0.90, 0.10])
    internet_service = rng.choice(["DSL", "Fiber optic", "No"],
                                   n_customers, p=[0.34, 0.44, 0.22])
    online_security = np.where(internet_service == "No", "No internet",
                                rng.choice(["Yes", "No"], n_customers, p=[0.40, 0.60]))
    tech_support = np.where(internet_service == "No", "No internet",
                             rng.choice(["Yes", "No"], n_customers, p=[0.35, 0.65]))
    streaming_tv = np.where(internet_service == "No", "No internet",
                             rng.choice(["Yes", "No"], n_customers, p=[0.45, 0.55]))
    streaming_movies = np.where(internet_service == "No", "No internet",
                                 rng.choice(["Yes", "No"], n_customers, p=[0.45, 0.55]))

    base_charge = np.where(internet_service == "Fiber optic", 70,
                  np.where(internet_service == "DSL", 45, 20))
    monthly_charges = (base_charge + rng.normal(0, 10, n_customers)).clip(18, 120).round(2)
    total_charges = (monthly_charges * tenure + rng.normal(0, 50, n_customers)).clip(0).round(2)

    tech_support_calls = rng.poisson(lam=2, size=n_customers)
    avg_monthly_usage_gb = (rng.lognormal(mean=3, sigma=0.8, size=n_customers)).round(1)
    contract_renewals = np.where(contract == "Month-to-month", 0,
                        np.where(contract == "One year", (tenure // 12).astype(int),
                                 (tenure // 24).astype(int)))
    last_interaction_days = rng.exponential(scale=30, size=n_customers).clip(0, 180).astype(int)
    satisfaction_score = rng.choice([1, 2, 3, 4, 5], n_customers, p=[0.08, 0.12, 0.30, 0.30, 0.20])

    # Churn probability based on features
    churn_prob = 0.05
    churn_prob += np.where(contract == "Month-to-month", 0.25, 0)
    churn_prob += np.where(contract == "Two year", -0.10, 0)
    churn_prob += np.where(internet_service == "Fiber optic", 0.10, 0)
    churn_prob += np.where(payment_method == "Electronic check", 0.10, 0)
    churn_prob += np.where(tenure < 12, 0.15, 0)
    churn_prob += np.where(tenure > 48, -0.10, 0)
    churn_prob += np.where(tech_support_calls > 4, 0.10, 0)
    churn_prob += np.where(satisfaction_score <= 2, 0.15, 0)
    churn_prob += np.where(satisfaction_score >= 4, -0.05, 0)
    churn_prob += np.where(monthly_charges > 80, 0.08, 0)
    churn_prob += np.where(online_security == "Yes", -0.05, 0)
    churn_prob += np.where(tech_support == "Yes", -0.05, 0)
    churn_prob += rng.normal(0, 0.05, n_customers)
    churn_prob = np.clip(churn_prob, 0.02, 0.95)
    churn = (rng.uniform(0, 1, n_customers) < churn_prob).astype(int)

    df = pd.DataFrame({
        "customer_id": customer_id, "gender": gender, "senior_citizen": senior_citizen,
        "partner": partner, "dependents": dependents, "tenure": tenure,
        "phone_service": phone_service, "internet_service": internet_service,
        "online_security": online_security, "tech_support": tech_support,
        "streaming_tv": streaming_tv, "streaming_movies": streaming_movies,
        "contract": contract, "paperless_billing": paperless,
        "payment_method": payment_method, "monthly_charges": monthly_charges,
        "total_charges": total_charges, "tech_support_calls": tech_support_calls,
        "avg_monthly_usage_gb": avg_monthly_usage_gb,
        "contract_renewals": contract_renewals.astype(int),
        "last_interaction_days": last_interaction_days,
        "satisfaction_score": satisfaction_score, "churn": churn,
    })
    return df


if __name__ == "__main__":
    df = generate_churn_data(5000)
    print(f"Generated {len(df)} customers. Churn rate: {df['churn'].mean():.2%}")
    df.to_csv("churn_data.csv", index=False)
    print("Saved to churn_data.csv")
