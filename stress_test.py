#!/usr/bin/env python3
"""
Advanced Stress Testing Suite for Watermarking/Blockchain Application
Usage: python stress_test.py [test_type] [options]
"""

import argparse
import concurrent.futures
import queue
import random
import sys
import threading
import time
from datetime import datetime
from typing import Dict

import requests


class AggressiveStressTester:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AggressiveWatermarkStressTester/2.0',
            'Content-Type': 'application/x-www-form-urlencoded'
        })
        self.results = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'response_times': [],
            'errors': [],
            'start_time': None,
            'end_time': None
        }
        self.lock = threading.Lock()

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {message}")
        
    def record_operation(self, success: bool, response_time: float, error: str = None):
        """Thread-safe operation recording"""
        with self.lock:
            self.results['total_operations'] += 1
            if success:
                self.results['successful_operations'] += 1
            else:
                self.results['failed_operations'] += 1
                if error:
                    self.results['errors'].append(error)
            self.results['response_times'].append(response_time)

    def test_connection(self):
        """Test if the application is reachable"""
        try:
            response = self.session.get(f"{self.base_url}/blockchain/stats/", timeout=10)
            if response.status_code == 200:
                stats = response.json()
                self.log(f"✅ Connection successful! Blockchain length: {stats.get('chain_length', 0)}")
                return True
            else:
                self.log(f"❌ Connection failed with status: {response.status_code}")
                return False
        except Exception as e:
            self.log(f"❌ Connection error: {e}")
            return False

    def extreme_mining_stress(self, num_blocks=100, concurrent_threads=20, duration_seconds=300):
        """Extreme mining stress test with high concurrency"""
        self.log(f"🔥 Starting EXTREME mining stress test:")
        self.log(f"   Target: {num_blocks} blocks, {concurrent_threads} threads, {duration_seconds}s duration")

        self.results['start_time'] = time.time()

        def mining_worker(worker_id):
            blocks_mined = 0
            while time.time() - self.results['start_time'] < duration_seconds and blocks_mined < num_blocks // concurrent_threads:
                start_time = time.time()
                try:
                    response = self.session.post(f"{self.base_url}/blockchain/async-mine/",
                                               data={'worker_id': worker_id}, timeout=30)
                    response_time = time.time() - start_time

                    if response.status_code == 200:
                        blocks_mined += 1
                        self.record_operation(True, response_time)
                        if blocks_mined % 10 == 0:
                            self.log(f"Worker {worker_id}: {blocks_mined} blocks mined")
                    else:
                        self.record_operation(False, response_time, f"HTTP {response.status_code}")

                except Exception as e:
                    response_time = time.time() - start_time
                    self.record_operation(False, response_time, str(e))

                # Brief pause to prevent overwhelming
                time.sleep(random.uniform(0.01, 0.05))

            self.log(f"Worker {worker_id} finished: {blocks_mined} blocks")

        # Launch mining threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_threads) as executor:
            futures = [executor.submit(mining_worker, i) for i in range(concurrent_threads)]

            # Monitor progress
            while any(not f.done() for f in futures):
                time.sleep(5)
                with self.lock:
                    ops_per_sec = self.results['total_operations'] / max(time.time() - self.results['start_time'], 1)
                    success_rate = (self.results['successful_operations'] / max(self.results['total_operations'], 1)) * 100
                    self.log(f"📊 Progress: {self.results['total_operations']} ops, "
                           f"{ops_per_sec:.2f} ops/sec, {success_rate:.1f}% success")

        self.results['end_time'] = time.time()
        return self._generate_report()

    def watermark_bombardment(self, num_operations=500, concurrent_threads=15, file_size_kb=1024):
        """Bombard the watermarking system with high-volume requests"""
        self.log(f"💥 Starting watermark BOMBARDMENT:")
        self.log(f"   Target: {num_operations} operations, {concurrent_threads} threads, {file_size_kb}KB files")

        # Generate test data
        test_data = b'X' * (file_size_kb * 1024)  # Create large test file data

        self.results['start_time'] = time.time()

        def watermark_worker(worker_id):
            operations = 0
            target_ops = num_operations // concurrent_threads

            while operations < target_ops:
                start_time = time.time()
                try:
                    # Simulate file upload with large data
                    files = {'image': ('test_image.png', test_data, 'image/png')}
                    data = {
                        'watermark_text': f'STRESS_TEST_WORKER_{worker_id}_{operations}',
                        'strength': random.uniform(0.1, 1.0)
                    }

                    response = self.session.post(f"{self.base_url}/stress-test/watermarking/",
                                               json=data, timeout=60)
                    response_time = time.time() - start_time

                    if response.status_code == 200:
                        operations += 1
                        self.record_operation(True, response_time)
                    else:
                        self.record_operation(False, response_time, f"HTTP {response.status_code}")

                except Exception as e:
                    response_time = time.time() - start_time
                    self.record_operation(False, response_time, str(e))

                # Very brief pause
                time.sleep(random.uniform(0.001, 0.01))

            self.log(f"Watermark worker {worker_id} completed {operations} operations")

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_threads) as executor:
            futures = [executor.submit(watermark_worker, i) for i in range(concurrent_threads)]

            # Real-time monitoring
            while any(not f.done() for f in futures):
                time.sleep(3)
                with self.lock:
                    elapsed = time.time() - self.results['start_time']
                    ops_per_sec = self.results['total_operations'] / max(elapsed, 1)
                    avg_response = sum(self.results['response_times']) / max(len(self.results['response_times']), 1)
                    self.log(f"💥 Bombardment: {self.results['total_operations']} ops, "
                           f"{ops_per_sec:.2f} ops/sec, {avg_response:.3f}s avg response")

        self.results['end_time'] = time.time()
        return self._generate_report()

    def chaos_mode(self, duration_seconds=600, max_concurrent_ops=50):
        """Chaos mode: Random mix of all operations at maximum intensity"""
        self.log(f"🌪️  CHAOS MODE ACTIVATED!")
        self.log(f"   Duration: {duration_seconds}s, Max concurrent: {max_concurrent_ops}")

        operations = [
            ('mine', 0.3),
            ('watermark', 0.4),
            ('reveal', 0.2),
            ('stats', 0.1)
        ]

        self.results['start_time'] = time.time()
        operation_queue = queue.Queue(maxsize=max_concurrent_ops * 2)

        def chaos_worker(worker_id):
            while time.time() - self.results['start_time'] < duration_seconds:
                try:
                    op_type = operation_queue.get(timeout=1)
                    start_time = time.time()

                    try:
                        if op_type == 'mine':
                            response = self.session.post(f"{self.base_url}/blockchain/async-mine/",
                                                       data={'chaos_worker': worker_id}, timeout=45)
                        elif op_type == 'watermark':
                            data = {'watermark_text': f'CHAOS_{worker_id}'}
                            response = self.session.post(f"{self.base_url}/stress-test/watermarking/",
                                                       json=data, timeout=30)
                        elif op_type == 'reveal':
                            response = self.session.get(f"{self.base_url}/reveal/", timeout=15)
                        else:  # stats
                            response = self.session.get(f"{self.base_url}/blockchain/stats/", timeout=10)

                        response_time = time.time() - start_time
                        self.record_operation(response.status_code == 200, response_time)

                    except Exception as e:
                        response_time = time.time() - start_time
                        self.record_operation(False, response_time, str(e))

                    operation_queue.task_done()

                except queue.Empty:
                    continue

        def operation_generator():
            """Generate random operations"""
            while time.time() - self.results['start_time'] < duration_seconds:
                op_type = random.choices([op[0] for op in operations],
                                       weights=[op[1] for op in operations])[0]
                try:
                    operation_queue.put(op_type, timeout=0.1)
                except queue.Full:
                    pass
                time.sleep(random.uniform(0.001, 0.01))

        # Start operation generator
        generator_thread = threading.Thread(target=operation_generator)
        generator_thread.daemon = True
        generator_thread.start()

        # Start chaos workers
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent_ops) as executor:
            futures = [executor.submit(chaos_worker, i) for i in range(max_concurrent_ops)]

            # Monitoring with more frequent updates
            while any(not f.done() for f in futures) and time.time() - self.results['start_time'] < duration_seconds:
                time.sleep(2)
                with self.lock:
                    elapsed = time.time() - self.results['start_time']
                    ops_per_sec = self.results['total_operations'] / max(elapsed, 1)
                    success_rate = (self.results['successful_operations'] / max(self.results['total_operations'], 1)) * 100
                    queue_size = operation_queue.qsize()
                    self.log(f"🌪️  CHAOS: {self.results['total_operations']} ops, "
                           f"{ops_per_sec:.2f} ops/sec, {success_rate:.1f}% success, queue: {queue_size}")

        self.results['end_time'] = time.time()
        return self._generate_report()

    def endurance_test(self, duration_hours=2, steady_ops_per_second=10):
        """Long-running endurance test"""
        duration_seconds = duration_hours * 3600
        self.log(f"🏃‍♂️ Starting ENDURANCE test: {duration_hours}h at {steady_ops_per_second} ops/sec")

        self.results['start_time'] = time.time()

        def endurance_worker():
            operation_count = 0
            target_interval = 1.0 / steady_ops_per_second

            while time.time() - self.results['start_time'] < duration_seconds:
                cycle_start = time.time()

                try:
                    # Rotate between different operations
                    ops = ['mine', 'watermark', 'stats']
                    op_type = ops[operation_count % len(ops)]

                    start_time = time.time()

                    if op_type == 'mine':
                        response = self.session.post(f"{self.base_url}/blockchain/async-mine/",
                                                   data={'endurance_test': True}, timeout=60)
                    elif op_type == 'watermark':
                        data = {'watermark_text': f'ENDURANCE_{operation_count}'}
                        response = self.session.post(f"{self.base_url}/stress-test/watermarking/",
                                                   json=data, timeout=45)
                    else:  # stats
                        response = self.session.get(f"{self.base_url}/blockchain/stats/", timeout=15)

                    response_time = time.time() - start_time
                    self.record_operation(response.status_code == 200, response_time)
                    operation_count += 1

                    # Log progress every 1000 operations
                    if operation_count % 1000 == 0:
                        elapsed_hours = (time.time() - self.results['start_time']) / 3600
                        with self.lock:
                            avg_response = sum(self.results['response_times']) / len(self.results['response_times'])
                            success_rate = (self.results['successful_operations'] / self.results['total_operations']) * 100
                            self.log(f"🏃‍♂️ Endurance {elapsed_hours:.1f}h: {operation_count} ops, "
                                   f"{avg_response:.3f}s avg, {success_rate:.1f}% success")

                except Exception as e:
                    response_time = time.time() - start_time
                    self.record_operation(False, response_time, str(e))

                # Maintain steady rate
                cycle_time = time.time() - cycle_start
                sleep_time = max(0, target_interval - cycle_time)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        # Run endurance test
        endurance_worker()

        self.results['end_time'] = time.time()
        return self._generate_report()

    def _generate_report(self) -> Dict:
        """Generate comprehensive test report"""
        if not self.results['response_times']:
            return {'error': 'No operations completed'}

        elapsed_time = self.results['end_time'] - self.results['start_time']
        response_times = sorted(self.results['response_times'])

        report = {
            'summary': {
                'total_operations': self.results['total_operations'],
                'successful_operations': self.results['successful_operations'],
                'failed_operations': self.results['failed_operations'],
                'success_rate_percent': (self.results['successful_operations'] / self.results['total_operations']) * 100,
                'duration_seconds': elapsed_time,
                'operations_per_second': self.results['total_operations'] / elapsed_time,
            },
            'performance': {
                'avg_response_time': sum(response_times) / len(response_times),
                'min_response_time': min(response_times),
                'max_response_time': max(response_times),
                'p50_response_time': response_times[len(response_times) // 2],
                'p95_response_time': response_times[int(len(response_times) * 0.95)],
                'p99_response_time': response_times[int(len(response_times) * 0.99)],
            },
            'errors': {
                'total_errors': len(self.results['errors']),
                'unique_errors': list(set(self.results['errors']))[:10],  # Top 10 unique errors
            }
        }

        # Print report
        self.log("=" * 60)
        self.log("📊 STRESS TEST REPORT")
        self.log("=" * 60)
        self.log(f"Total Operations: {report['summary']['total_operations']:,}")
        self.log(f"Success Rate: {report['summary']['success_rate_percent']:.2f}%")
        self.log(f"Operations/Second: {report['summary']['operations_per_second']:.2f}")
        self.log(f"Duration: {report['summary']['duration_seconds']:.1f}s")
        self.log(f"Avg Response Time: {report['performance']['avg_response_time']:.3f}s")
        self.log(f"P95 Response Time: {report['performance']['p95_response_time']:.3f}s")
        self.log(f"P99 Response Time: {report['performance']['p99_response_time']:.3f}s")
        self.log(f"Total Errors: {report['errors']['total_errors']}")

        return report

def main():
    parser = argparse.ArgumentParser(description='Aggressive Stress Testing Suite')
    parser.add_argument('test_type', choices=['extreme_mining', 'watermark_bombardment', 'chaos', 'endurance', 'all'],
                       help='Type of stress test to run')
    parser.add_argument('--url', default='http://127.0.0.1:8000', help='Base URL of the application')
    parser.add_argument('--threads', type=int, default=20, help='Number of concurrent threads')
    parser.add_argument('--duration', type=int, default=300, help='Test duration in seconds')
    parser.add_argument('--operations', type=int, default=1000, help='Number of operations')

    args = parser.parse_args()
    
    tester = AggressiveStressTester(args.url)

    if not tester.test_connection():
        sys.exit(1)

    try:
        if args.test_type == 'extreme_mining':
            tester.extreme_mining_stress(args.operations, args.threads, args.duration)
        elif args.test_type == 'watermark_bombardment':
            tester.watermark_bombardment(args.operations, args.threads)
        elif args.test_type == 'chaos':
            tester.chaos_mode(args.duration, args.threads)
        elif args.test_type == 'endurance':
            tester.endurance_test(duration_hours=args.duration/3600)
        elif args.test_type == 'all':
            tester.log("🔥 Running ALL stress tests!")
            tester.extreme_mining_stress(200, 15, 180)
            time.sleep(30)  # Cool down
            tester.watermark_bombardment(300, 12)
            time.sleep(30)  # Cool down
            tester.chaos_mode(240, 25)

    except KeyboardInterrupt:
        tester.log("❌ Test interrupted by user")
    except Exception as e:
        tester.log(f"❌ Test failed with error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
