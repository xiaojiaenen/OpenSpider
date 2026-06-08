from openspider.core.sinks.base import BaseSink
from openspider.core.sinks.csv_sink import CsvSink
from openspider.core.sinks.excel_sink import ExcelSink
from openspider.core.sinks.json_sink import JsonSink
from openspider.core.sinks.kafka_sink import KafkaSink
from openspider.core.sinks.doris_sink import DorisSink
from openspider.core.sinks.parquet_sink import ParquetSink
from openspider.core.sinks.database_sink import DatabaseSink

SINK_REGISTRY = {
    "csv": CsvSink,
    "excel": ExcelSink,
    "json": JsonSink,
    "kafka": KafkaSink,
    "doris": DorisSink,
    "parquet": ParquetSink,
    "database": DatabaseSink,
}

def get_sink_class(sink_type: str):
    return SINK_REGISTRY.get(sink_type)