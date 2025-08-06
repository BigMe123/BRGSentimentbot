"""Streaming analytics using Spark Structured Streaming."""
from __future__ import annotations

from pyspark.sql import SparkSession
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


def start_stream(kafka_bootstrap: str, topic: str) -> None:
    spark = (
        SparkSession.builder.appName("sentiment-stream")
        .getOrCreate()
    )
    df = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", kafka_bootstrap)
        .option("subscribe", topic)
        .load()
    )
    df = df.selectExpr("CAST(value AS STRING) as text")
    analyzer = SentimentIntensityAnalyzer()

    def analyze(text: str) -> str:
        return str(analyzer.polarity_scores(text)["compound"])

    sentiment_udf = udf(analyze, StringType())
    out = df.withColumn("sentiment", sentiment_udf(df.text))
    query = (
        out.selectExpr("to_json(struct(*)) AS value")
        .writeStream.format("kafka")
        .option("kafka.bootstrap.servers", kafka_bootstrap)
        .option("topic", f"{topic}-out")
        .outputMode("update")
        .start()
    )
    query.awaitTermination()
