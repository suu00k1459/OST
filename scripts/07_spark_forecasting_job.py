from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, lit
import os

# DB connection settings (from docker-compose)
DB_HOST = os.getenv("DB_HOST", "timescaledb")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "flead")
DB_USER = os.getenv("DB_USER", "flead")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

JDBC_URL = f"jdbc:postgresql://{DB_HOST}:{DB_PORT}/{DB_NAME}"
JDBC_PROPERTIES = {
    "user": DB_USER,
    "password": DB_PASSWORD,
    "driver": "org.postgresql.Driver",
}

def main():
    # Create Spark session
    spark = (
        SparkSession.builder
        .appName("OST Spark Forecasting Job")
        .getOrCreate()
    )

    print("=== Spark Forecasting Job Started ===")

    # مثال بسيط: نكتب 5 صفوف dummy في device_forecast
    # بعدين نعدل ده ونخليه يقرأ داتا حقيقية ويطلع forecast فعلاً
    data = [
        (1, "temperature", 10.0, 15),
        (2, "temperature", 20.0, 15),
        (3, "temperature", 30.0, 15),
        (1, "humidity", 40.0, 30),
        (2, "humidity", 50.0, 30),
    ]

    df = spark.createDataFrame(
        data,
        schema="""
            device_id INT,
            metric_name STRING,
            forecast_value DOUBLE,
            horizon_minutes INT
        """
    )

    # نضيف ts و created_at جوه Spark
    df = (
        df
        .withColumn("ts", current_timestamp())
        .withColumn("created_at", current_timestamp())
    )

    # نرتب الأعمدة بحيث تطابق جدول device_forecast:
    # device_id, metric_name, ts, forecast_value, horizon_minutes, created_at
    df_final = df.select(
        "device_id",
        "metric_name",
        "ts",
        "forecast_value",
        "horizon_minutes",
        "created_at"
    )

    print("Writing dummy forecast data into device_forecast table...")

    (
        df_final
        .write
        .mode("append")
        .jdbc(JDBC_URL, "device_forecast", properties=JDBC_PROPERTIES)
    )

    print("=== Spark Forecasting Job Finished Successfully ===")

    spark.stop()

if __name__ == "__main__":
    main()
