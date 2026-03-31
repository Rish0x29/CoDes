"""Glue ETL job - Clean, deduplicate, and transform data."""

import sys
from pyspark.context import SparkContext
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import DoubleType, TimestampType

try:
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    GLUE_ENV = True
except ImportError:
    GLUE_ENV = False


def clean_transactions(df):
    result = df.dropDuplicates(["transaction_id"])
    result = result.filter(F.col("amount").isNotNull())
    result = result.withColumn("amount", F.col("amount").cast(DoubleType()))
    result = result.filter(F.col("amount") > 0)
    result = result.withColumn("timestamp", F.to_timestamp(F.col("timestamp")))
    result = result.filter(F.col("timestamp").isNotNull())
    result = result.withColumn("date", F.to_date(F.col("timestamp")))
    result = result.withColumn("hour", F.hour(F.col("timestamp")))
    result = result.withColumn("day_of_week", F.dayofweek(F.col("timestamp")))
    result = result.withColumn("amount_bucket",
        F.when(F.col("amount") < 10, "micro")
         .when(F.col("amount") < 50, "small")
         .when(F.col("amount") < 200, "medium")
         .when(F.col("amount") < 1000, "large")
         .otherwise("xlarge"))
    return result


def clean_customers(df):
    result = df.dropDuplicates(["customer_id"])
    result = result.filter(F.col("email").isNotNull())
    result = result.withColumn("email", F.lower(F.trim(F.col("email"))))
    result = result.withColumn("name", F.trim(F.col("name")))
    result = result.withColumn("created_at", F.to_timestamp(F.col("created_at")))
    return result


def clean_products(df):
    result = df.dropDuplicates(["product_id"])
    result = result.withColumn("price", F.col("price").cast(DoubleType()))
    result = result.filter(F.col("price") > 0)
    result = result.withColumn("name", F.trim(F.col("name")))
    result = result.withColumn("category", F.lower(F.trim(F.col("category"))))
    return result


CLEANERS = {
    "transactions": clean_transactions,
    "customers": clean_customers,
    "products": clean_products,
}


def run_etl(input_path: str, output_path: str, data_type: str, spark=None):
    if spark is None:
        spark = SparkSession.builder.appName("DataLakeETL").getOrCreate()

    df = spark.read.option("header", "true").option("inferSchema", "true").csv(input_path)
    initial_count = df.count()
    print(f"Read {initial_count} records of type '{data_type}'")

    cleaner = CLEANERS.get(data_type)
    if cleaner:
        df = cleaner(df)
    else:
        df = df.dropDuplicates()

    final_count = df.count()
    dropped = initial_count - final_count
    print(f"After cleaning: {final_count} records ({dropped} removed)")

    df = df.withColumn("_etl_timestamp", F.current_timestamp())
    df = df.withColumn("_source_file", F.input_file_name())

    if "date" in df.columns:
        df.write.mode("overwrite").partitionBy("date").parquet(output_path)
    else:
        df.write.mode("overwrite").parquet(output_path)

    print(f"Wrote {final_count} records to {output_path}")
    return df


if GLUE_ENV:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "input_path", "output_path", "data_type"])
    sc = SparkContext()
    glueContext = GlueContext(sc)
    spark = glueContext.spark_session
    job = Job(glueContext)
    job.init(args["JOB_NAME"], args)
    run_etl(args["input_path"], args["output_path"], args["data_type"], spark)
    job.commit()
