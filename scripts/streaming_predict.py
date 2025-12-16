import json
from typing import Dict, Any

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, abs as ps_abs, greatest, lit
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType


def load_model(model_path: str) -> Dict[str, Any]:
    with open(model_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    # ----------------------------
    # Config
    # ----------------------------
    KAFKA_BOOTSTRAP = "localhost:9092"
    INPUT_TOPIC = "sensors"
    MODEL_PATH = "model.json"

    THRESHOLD = 3.0          # نفس threshold بتاعك
    AGGREGATE = "max"        # هنشتغل هنا max (الأبسط للشرح)
    CHECKPOINT = "/tmp/zscore_stream_ckpt"
    OUTPUT_PATH = "/tmp/zscore_stream_out"   # parquet output (بدّلها لو عايز sink تاني)

    # ----------------------------
    # Spark Session
    # ----------------------------
    spark = (
        SparkSession.builder
        .appName("ZScoreStreamingPredict")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # ----------------------------
    # Load model stats
    # model.json contains: feature_cols + stats{feature:{center,scale}}
    # ----------------------------
    model = load_model(MODEL_PATH)
    feature_cols = model["feature_cols"]
    stats = model["stats"]

    # ----------------------------
    # Define schema for incoming JSON
    # (include your id/time cols + numeric features)
    # ----------------------------
    # عدّل ده حسب أعمدتك الحقيقية
    schema_fields = [
        StructField("device_id", IntegerType(), True),
        StructField("ts", StringType(), True),
    ] + [StructField(c, DoubleType(), True) for c in feature_cols]

    event_schema = StructType(schema_fields)

    # ----------------------------
    # Read stream from Kafka
    # ----------------------------
    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", INPUT_TOPIC)
        .option("startingOffsets", "latest")
        .load()
    )

    # Kafka value is bytes => cast to string
    parsed = (
        raw.selectExpr("CAST(value AS STRING) AS json_str")
        .select(from_json(col("json_str"), event_schema).alias("e"))
        .select("e.*")
    )

    # ----------------------------
    # Compute per-feature z-scores: z = (x-center)/scale
    # then abs(z), aggregate, label
    # ----------------------------
    z_abs_cols = []
    scored = parsed

    for c in feature_cols:
        center = float(stats[c]["center"])
        scale = float(stats[c]["scale"])

        # abs((col - center) / scale)
        zc = ps_abs((col(c) - lit(center)) / lit(scale)).alias(f"absz_{c}")
        scored = scored.withColumn(f"absz_{c}", zc)
        z_abs_cols.append(col(f"absz_{c}"))

    if AGGREGATE.lower() == "max":
        anomaly_score = greatest(*z_abs_cols)
    else:
        # لو عايز mean/rms/count نقدر نضيفهم، بس max كفاية للامتحان
        anomaly_score = greatest(*z_abs_cols)

    out = (
        scored
        .withColumn("anomaly_score", anomaly_score)
        .withColumn("is_anomaly", (col("anomaly_score") > lit(THRESHOLD)).cast("int"))
    )

    # ----------------------------
    # Write stream (Parquet sink example)
    # ممكن تغيرها لـ console أو JDBC أو Kafka output
    # ----------------------------
    query = (
        out.writeStream
        .format("parquet")
        .option("path", OUTPUT_PATH)
        .option("checkpointLocation", CHECKPOINT)
        .outputMode("append")
        .start()
    )

    query.awaitTermination()


if __name__ == "__main__":
    main()
