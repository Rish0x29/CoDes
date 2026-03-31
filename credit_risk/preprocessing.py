"""Feature engineering pipeline for credit risk scoring."""

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder, OrdinalEncoder
from sklearn.impute import SimpleImputer
import joblib


NUMERIC_FEATURES = [
    "annual_income", "employment_length", "loan_amount", "interest_rate",
    "loan_term", "credit_score", "dti_ratio", "num_credit_lines",
    "revolving_utilization", "delinquencies_2yr", "public_records",
    "total_accounts", "months_since_last_delinq",
]

CATEGORICAL_FEATURES = ["home_ownership", "purpose"]

DERIVED_FEATURES = [
    "debt_to_income_ratio", "credit_utilization_x_delinq",
    "loan_to_income_ratio", "income_per_credit_line",
    "monthly_payment_estimate", "risk_score_composite",
]


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["debt_to_income_ratio"] = result["loan_amount"] / result["annual_income"].clip(lower=1)
    result["credit_utilization_x_delinq"] = result["revolving_utilization"] * (result["delinquencies_2yr"] + 1)
    result["loan_to_income_ratio"] = result["loan_amount"] / result["annual_income"].clip(lower=1)
    result["income_per_credit_line"] = result["annual_income"] / result["num_credit_lines"].clip(lower=1)

    monthly_rate = result["interest_rate"] / 100 / 12
    n_payments = result["loan_term"]
    result["monthly_payment_estimate"] = (
        result["loan_amount"] * monthly_rate * (1 + monthly_rate)**n_payments
        / ((1 + monthly_rate)**n_payments - 1)
    )
    result["monthly_payment_estimate"] = result["monthly_payment_estimate"].fillna(0)

    result["risk_score_composite"] = (
        (850 - result["credit_score"]) / 550 * 0.3
        + result["dti_ratio"] / 50 * 0.2
        + result["revolving_utilization"].clip(upper=1.5) * 0.2
        + result["delinquencies_2yr"] / 7 * 0.15
        + result["public_records"] / 3 * 0.15
    )
    return result


def build_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="UNKNOWN")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])

    all_numeric = NUMERIC_FEATURES + DERIVED_FEATURES
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, all_numeric),
            ("cat", categorical_pipeline, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )
    return preprocessor


def preprocess_data(df: pd.DataFrame, preprocessor=None, fit: bool = True):
    df_features = add_derived_features(df)

    target = None
    if "default" in df_features.columns:
        target = df_features["default"].values
        df_features = df_features.drop(columns=["default"])

    if preprocessor is None:
        preprocessor = build_preprocessor()

    if fit:
        X = preprocessor.fit_transform(df_features)
    else:
        X = preprocessor.transform(df_features)

    feature_names = (NUMERIC_FEATURES + DERIVED_FEATURES +
                     list(preprocessor.named_transformers_["cat"]
                          .named_steps["encoder"]
                          .get_feature_names_out(CATEGORICAL_FEATURES)))

    return X, target, preprocessor, feature_names


def save_preprocessor(preprocessor, path: str = "preprocessor.joblib"):
    joblib.dump(preprocessor, path)


def load_preprocessor(path: str = "preprocessor.joblib"):
    return joblib.load(path)
