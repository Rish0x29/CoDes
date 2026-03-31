"""AWS Glue ETL job for churn data processing using PySpark."""

import sys
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType

try:
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    GLUE_ENV = True
except ImportError:
    GLUE_ENV = False


def create_features(df):
    """Create behavioral and derived features."""
    result = df

    # Tenure buckets
    result = result.withColumn("tenure_bucket",
        F.when(F.col("tenure") <= 6, "0-6m")
         .when(F.col("tenure") <= 12, "6-12m")
         .when(F.col("tenure") <= 24, "1-2y")
         .when(F.col("tenure") <= 48, "2-4y")
         .otherwise("4y+"))

    # Monthly charge buckets
    result = result.withColumn("charge_bucket",
        F.when(F.col("monthly_charges") < 30, "low")
         .when(F.col("monthly_charges") < 60, "medium")
         .when(F.col("monthly_charges") < 90, "high")
         .otherwise("very_high"))

    # Avg charge per month of tenure
    result = result.withColumn("avg_charge_per_tenure",
        F.round(F.col("total_charges") / F.greatest(F.col("tenure"), F.lit(1)), 2))

    # Service count
    service_cols = ["phone_service", "online_security", "tech_support", "streaming_tv", "streaming_movies"]
    for col_name in service_cols:
        result = result.withColumn(f"{col_name}_flag",
            F.when(F.col(col_name) == "Yes", 1).otherwise(0))

    result = result.withColumn("total_services",
        sum(F.col(f"{c}_flag") for c in service_cols))

    # Has internet
    result = result.withColumn("has_internet",
        F.when(F.col("internet_service") != "No", 1).otherwise(0))

    # Engagement score
    result = result.withColumn("engagement_score",
        F.round((F.col("total_services") * 0.3 +
                 F.least(F.col("tenure"), F.lit(60)) / 60 * 0.3 +
                 F.col("satisfaction_score") / 5 * 0.4), 4))

    # Risk flags
    result = result.withColumn("high_risk_contract",
        F.when((F.col("contract") == "Month-to-month") & (F.col("tenure") < 12), 1).otherwise(0))

    result = result.withColumn("high_risk_payment",
        F.when(F.col("payment_method") == "Electronic check", 1).otherwise(0))

    # Drop intermediate flag columns
    for col_name in service_cols:
        result = result.drop(f"{col_name}_flag")

    return result


def clean_data(df):
    """Clean and validate data."""
    result = df

    # Cast types
    result = result.withColumn("monthly_charges", F.col("monthly_charges").cast(DoubleType()))
    result = result.withColumn("total_charges", F.col("total_charges").cast(DoubleType()))
    result = result.withColumn("tenure", F.col("tenure").cast(IntegerType()))

    # Handle nulls
    result = result.fillna({"total_charges": 0.0, "monthly_charges": 0.0, "tenure": 0})

    # Remove duplicates
    result = result.dropDuplicates(["customer_id"])

    # Filter obvious outliers
    result = result.filter(F.col("monthly_charges") >= 0)
    result = result.filter(F.col("tenure") >= 0)

    return result


def run_etl(input_path: str, output_path: str, spark=None):
    """Main ETL function."""
    if spark is None:
        spark = SparkSession.builder.appName("ChurnETL").getOrCreate()

    df = spark.read.option("header", "true").option("inferSchema", "true").csv(input_path)
    print(f"Read {df.count()} records from {input_path}")

    df = clean_data(df)
    print(f"After cleaning: {df.count()} records")

    df = create_features(df)
    print(f"After feature engineering: {len(df.columns)} columns")

    # Add processing metadata
    df = df.withColumn("processed_date", F.current_date())

    # Write partitioned parquet
    df.write.mode("overwrite").partitionBy("processed_date").parquet(output_path)
    print(f"Wrote to {output_path}")

    return df


if GLUE_ENV:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "input_path", "output_path"])
    sc = SparkContext()
    glueContext = GlueContext(sc)
    spark = glueContext.spark_session
    job = Job(glueContext)
    job.init(args["JOB_NAME"], args)

    run_etl(args["input_path"], args["output_path"], spark)

    job.commit()
