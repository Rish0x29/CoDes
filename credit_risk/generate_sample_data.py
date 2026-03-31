"""Generate realistic synthetic credit data for training and testing."""

import numpy as np
import pandas as pd


def generate_credit_data(n_samples: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)

    annual_income = rng.lognormal(mean=10.8, sigma=0.6, size=n_samples).clip(15000, 500000)
    employment_length = rng.choice(range(0, 31), size=n_samples, p=_emp_probs())
    home_ownership = rng.choice(["RENT", "OWN", "MORTGAGE"], size=n_samples, p=[0.35, 0.15, 0.50])
    loan_amount = (annual_income * rng.uniform(0.05, 0.5, n_samples)).round(0)
    interest_rate = rng.uniform(5.0, 25.0, n_samples)
    loan_term = rng.choice([36, 60], size=n_samples, p=[0.6, 0.4])
    credit_score = rng.normal(700, 60, n_samples).clip(300, 850).astype(int)
    dti_ratio = rng.uniform(0, 45, n_samples).round(2)
    num_credit_lines = rng.poisson(lam=8, size=n_samples).clip(1, 40)
    revolving_utilization = rng.beta(2, 5, n_samples).clip(0, 1.5).round(4)
    delinquencies_2yr = rng.choice(range(0, 8), size=n_samples, p=[0.65, 0.18, 0.08, 0.04, 0.02, 0.01, 0.01, 0.01])
    public_records = rng.choice(range(0, 4), size=n_samples, p=[0.85, 0.10, 0.04, 0.01])
    total_accounts = num_credit_lines + rng.poisson(lam=5, size=n_samples)
    months_since_last_delinq = rng.choice([0, 6, 12, 24, 36, 48, 60, -1], size=n_samples,
                                           p=[0.3, 0.05, 0.05, 0.1, 0.1, 0.1, 0.1, 0.2])
    purpose = rng.choice(["debt_consolidation", "credit_card", "home_improvement", "major_purchase",
                           "medical", "car", "small_business", "other"],
                          size=n_samples, p=[0.35, 0.20, 0.10, 0.08, 0.05, 0.08, 0.06, 0.08])

    # Generate default labels based on risk factors
    default_prob = _compute_default_probability(
        credit_score, dti_ratio, revolving_utilization, delinquencies_2yr,
        public_records, interest_rate, employment_length, annual_income, loan_amount, rng
    )
    default = (rng.uniform(0, 1, n_samples) < default_prob).astype(int)

    df = pd.DataFrame({
        "annual_income": annual_income.round(0),
        "employment_length": employment_length,
        "home_ownership": home_ownership,
        "loan_amount": loan_amount,
        "interest_rate": interest_rate.round(2),
        "loan_term": loan_term,
        "credit_score": credit_score,
        "dti_ratio": dti_ratio,
        "num_credit_lines": num_credit_lines,
        "revolving_utilization": revolving_utilization,
        "delinquencies_2yr": delinquencies_2yr,
        "public_records": public_records,
        "total_accounts": total_accounts,
        "months_since_last_delinq": months_since_last_delinq,
        "purpose": purpose,
        "default": default,
    })
    return df


def _emp_probs():
    probs = np.array([0.08] + [0.06]*5 + [0.05]*5 + [0.03]*10 + [0.01]*10 + [0.005])
    return probs / probs.sum()


def _compute_default_probability(credit_score, dti, rev_util, delinq, pub_rec,
                                  interest, emp_len, income, loan_amt, rng):
    base = 0.05
    score_effect = np.clip((750 - credit_score) / 500, -0.1, 0.3)
    dti_effect = np.clip((dti - 20) / 100, -0.05, 0.15)
    util_effect = np.clip((rev_util - 0.3) * 0.3, -0.05, 0.15)
    delinq_effect = delinq * 0.04
    pub_rec_effect = pub_rec * 0.06
    rate_effect = np.clip((interest - 12) / 80, -0.03, 0.1)
    emp_effect = np.clip((5 - emp_len) * 0.005, -0.02, 0.03)
    ratio_effect = np.clip((loan_amt / income - 0.2) * 0.2, -0.02, 0.1)
    noise = rng.normal(0, 0.03, len(credit_score))

    prob = base + score_effect + dti_effect + util_effect + delinq_effect + pub_rec_effect + rate_effect + emp_effect + ratio_effect + noise
    return np.clip(prob, 0.01, 0.95)


if __name__ == "__main__":
    df = generate_credit_data(5000)
    print(f"Generated {len(df)} records")
    print(f"Default rate: {df['default'].mean():.2%}")
    print(f"\nSample:\n{df.head()}")
    df.to_csv("credit_data.csv", index=False)
    print("Saved to credit_data.csv")
