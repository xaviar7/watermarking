"""
Redis TimeSeries integration for watermarking/blockchain metrics
Provides high-performance time series data storage and querying
"""
import json
import logging
import os
import time
from typing import Optional, List, Dict, Any

import redis
from django.conf import settings

logger = logging.getLogger(__name__)


class RedisTimeSeriesManager:
    def __init__(self):
        self.redis_client = None
        self.timeseries_available = False
        self._connection_attempted = False

    def _get_redis_connection(self):
        """Lazy Redis connection with development/testing fallback"""
        if self.redis_client is not None or self._connection_attempted:
            return self.redis_client

        self._connection_attempted = True

        try:
            # Determine Redis host based on environment
            redis_host = 'redis' if os.environ.get('DOCKER_ENV') else 'localhost'
            redis_password = getattr(settings, 'REDIS_PASSWORD', None)

            self.redis_client = redis.Redis(
                host=redis_host,
                port=6379,
                password=redis_password,
                decode_responses=True,
                socket_connect_timeout=2,  # Quick timeout for tests
                socket_timeout=2
            )

            # Test the connection
            self.redis_client.ping()
            self.timeseries_available = self._check_timeseries_availability()
            logger.info(f"Redis connected successfully at {redis_host}:6379")

        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Operating in fallback mode.")
            self.redis_client = None
            self.timeseries_available = False

        return self.redis_client

    def _check_timeseries_availability(self):
        """Check if Redis TimeSeries module is available"""
        if not self.redis_client:
            return False

        try:
            # Try to execute a simple TimeSeries command
            self.redis_client.execute_command('TS.INFO', 'test_availability_check')
        except redis.exceptions.ResponseError as e:
            if "unknown command" in str(e).lower():
                logger.warning("Redis TimeSeries module not available. Falling back to regular Redis operations.")
                return False
            elif "TSDB: the key does not exist" in str(e):
                # This means TimeSeries is available but the key doesn't exist
                return True
        except Exception as e:
            logger.error(f"Error checking TimeSeries availability: {e}")
            return False
        return True

    def create_time_series(self, key: str, retention_ms: int = 3600000, labels: Dict[str, str] = None):
        """Create a new time series with optional labels and retention policy"""
        client = self._get_redis_connection()
        if not client:
            return False

        if not self.timeseries_available:
            # Fallback: just set a marker in regular Redis
            try:
                client.set(f"ts_fallback:{key}", json.dumps(labels or {}))
                return True
            except Exception as e:
                logger.error(f"Failed to create fallback time series {key}: {e}")
                return False

        try:
            # Use TS.CREATE with retention and labels
            cmd = ['TS.CREATE', key, 'RETENTION', retention_ms]
            if labels:
                for label_key, label_value in labels.items():
                    cmd.extend(['LABELS', label_key, label_value])

            client.execute_command(*cmd)
            return True
        except redis.exceptions.ResponseError as e:
            if "TSDB: key already exists" in str(e):
                return True  # Key exists, that's fine
            raise e

    def add_sample(self, key: str, value: float, timestamp: Optional[int] = None, labels: Dict[str, str] = None):
        """Add a sample to a time series"""
        if timestamp is None:
            timestamp = int(time.time() * 1000)  # Convert to milliseconds

        client = self._get_redis_connection()
        if not client:
            return False

        if not self.timeseries_available:
            # Fallback: store latest value in regular Redis hash
            client.hset(f"ts_fallback_data:{key}", "value", value, "timestamp", timestamp)
            return True

        try:
            # Try to add sample, create series if it doesn't exist
            try:
                client.execute_command('TS.ADD', key, timestamp, value)
            except redis.exceptions.ResponseError as e:
                if "TSDB: the key does not exist" in str(e):
                    # Create the series and try again
                    self.create_time_series(key, labels=labels)
                    client.execute_command('TS.ADD', key, timestamp, value)
                else:
                    raise e
            return True
        except Exception as e:
            logger.error(f"Error adding sample to {key}: {e}")
            return False

    def get_range(self, key: str, from_time: int, to_time: int,
                  aggregation_type: str = None, bucket_duration: int = None) -> List[tuple]:
        """Get time series data within a time range with optional aggregation"""
        client = self._get_redis_connection()
        if not client:
            return []

        try:
            cmd = ['TS.RANGE', key, from_time, to_time]

            if aggregation_type and bucket_duration:
                cmd.extend(['AGGREGATION', aggregation_type, bucket_duration])

            result = client.execute_command(*cmd)
            return [(int(ts), float(value)) for ts, value in result]
        except Exception as e:
            print(f"Error getting range for {key}: {e}")
            return []

    def get_latest(self, key: str) -> Optional[tuple]:
        """Get the latest sample from a time series"""
        client = self._get_redis_connection()
        if not client:
            return None

        try:
            result = client.execute_command('TS.GET', key)
            if result:
                return (int(result[0]), float(result[1]))
            return None
        except Exception as e:
            print(f"Error getting latest for {key}: {e}")
            return None

    def multi_get(self, filter_expr: str) -> Dict[str, tuple]:
        """Get latest values from multiple time series matching a filter"""
        client = self._get_redis_connection()
        if not client:
            return {}

        try:
            result = client.execute_command('TS.MGET', 'FILTER', filter_expr)
            return {
                key: (int(timestamp), float(value)) if timestamp and value else None
                for key, labels, timestamp, value in result
            }
        except Exception as e:
            print(f"Error in multi_get with filter {filter_expr}: {e}")
            return {}

    def create_rule(self, source_key: str, dest_key: str, aggregation_type: str, bucket_duration: int):
        """Create downsampling rule for automatic aggregation"""
        if not self.timeseries_available:
            # Skip rule creation when TimeSeries is not available
            logger.debug(f"Skipping rule creation for {source_key} -> {dest_key} (TimeSeries not available)")
            return True

        client = self._get_redis_connection()
        if not client:
            return False

        try:
            # Create destination series first
            self.create_time_series(dest_key, retention_ms=86400000)  # 24 hour retention for aggregated data

            # Create the rule
            client.execute_command(
                'TS.CREATERULE', source_key, dest_key,
                'AGGREGATION', aggregation_type, bucket_duration
            )
            return True
        except redis.exceptions.ResponseError as e:
            # Accept errors for rules that already exist
            if any(error_msg in str(e) for error_msg in [
                "TSDB: compaction rule already exists",
                "TSDB: the destination key already has a src rule"
            ]):
                return True
            logger.error(f"Error creating rule: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error creating rule: {e}")
            return False


# Global instance
redis_ts = RedisTimeSeriesManager()


class BlockchainMetricsCollector:
    """Collector for blockchain-specific metrics using Redis TimeSeries"""

    def __init__(self):
        self.ts_manager = redis_ts
        self._initialize_time_series()

    def _initialize_time_series(self):
        """Initialize all time series with proper labels and retention"""
        metrics = {
            'blockchain:length': {'type': 'gauge', 'unit': 'blocks'},
            'blockchain:pending_transactions': {'type': 'gauge', 'unit': 'count'},
            'blockchain:mining_duration': {'type': 'histogram', 'unit': 'seconds'},
            'blockchain:operations': {'type': 'counter', 'unit': 'operations'},
            'watermark:operations': {'type': 'counter', 'unit': 'operations'},
            'watermark:processing_time': {'type': 'histogram', 'unit': 'seconds'},
            'system:cpu_usage': {'type': 'gauge', 'unit': 'percent'},
            'system:memory_usage': {'type': 'gauge', 'unit': 'bytes'},
            'stress:operations_per_second': {'type': 'gauge', 'unit': 'ops/sec'},
            'stress:error_rate': {'type': 'gauge', 'unit': 'percent'},
            'stress:concurrent_operations': {'type': 'gauge', 'unit': 'count'},
            'blockchain:hash_rate': {'type': 'gauge', 'unit': 'hashes/sec'},
            'blockchain:difficulty': {'type': 'gauge', 'unit': 'difficulty'},
            'watermark:queue_depth': {'type': 'gauge', 'unit': 'count'}
        }

        for key, labels in metrics.items():
            # Create with 24-hour retention for detailed metrics
            self.ts_manager.create_time_series(key, retention_ms=86400000, labels=labels)

            # Create downsampling rules for high-frequency metrics
            if labels['type'] in ['gauge', 'histogram']:
                # 30-second aggregations for real-time monitoring
                self.ts_manager.create_rule(key, f"{key}:30s", "AVG", 30000)
                # 1-minute averages
                self.ts_manager.create_rule(key, f"{key}:1min", "AVG", 60000)
                # 5-minute averages
                self.ts_manager.create_rule(key, f"{key}:5min", "AVG", 300000)
                # 1-hour aggregations for long-term trends
                self.ts_manager.create_rule(key, f"{key}:1h", "AVG", 3600000)

    def record_blockchain_length(self, length: int):
        """Record current blockchain length"""
        self.ts_manager.add_sample('blockchain:length', float(length))

    def record_pending_transactions(self, count: int):
        """Record pending transactions count"""
        self.ts_manager.add_sample('blockchain:pending_transactions', float(count))

    def record_mining_duration(self, duration: float):
        """Record mining operation duration"""
        self.ts_manager.add_sample('blockchain:mining_duration', duration)

    def record_operation(self, operation_type: str, count: int = 1):
        """Record blockchain/watermark operations"""
        key = f"blockchain:operations:{operation_type}"
        self.ts_manager.add_sample(key, float(count))

    def record_watermark_operation(self, operation_type: str, duration: float = None):
        """Record watermarking operations"""
        self.ts_manager.add_sample(f'watermark:operations:{operation_type}', 1.0)
        if duration:
            self.ts_manager.add_sample('watermark:processing_time', duration)

    def get_realtime_metrics(self) -> Dict[str, Any]:
        """Get real-time metrics for dashboard"""
        latest_metrics = self.ts_manager.multi_get('type=gauge')

        # Get recent trends (last 5 minutes)
        current_time = int(time.time() * 1000)
        five_min_ago = current_time - (5 * 60 * 1000)

        trends = {}
        for key in ['blockchain:length', 'blockchain:pending_transactions']:
            data = self.ts_manager.get_range(key, five_min_ago, current_time)
            if len(data) > 1:
                trends[key] = {
                    'current': data[-1][1],
                    'trend': data[-1][1] - data[0][1],
                    'samples': len(data)
                }

        return {
            'latest': latest_metrics,
            'trends': trends,
            'timestamp': current_time
        }


# Global metrics collector instance
blockchain_metrics = BlockchainMetricsCollector()
