import os
import threading
import time
import uuid
from uuid import uuid4

from PIL import Image as PILImage, UnidentifiedImageError
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.files import File
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from stegano import lsb

from converter.blockchain import Blockchain
from converter.redis_timeseries import blockchain_metrics
from .models import Image

# Custom metrics for watermarking/blockchain
watermark_operations = Counter('watermark_operations_total', 'Total watermark operations', ['operation_type'])
blockchain_operations = Counter('blockchain_operations_total', 'Total blockchain operations', ['operation_type'])
mining_duration = Histogram('mining_duration_seconds', 'Time spent mining blocks')
blockchain_length = Gauge('blockchain_length', 'Current length of the blockchain')
pending_transactions = Gauge('pending_transactions_count', 'Number of pending transactions')
image_processing_duration = Histogram('image_processing_duration_seconds', 'Time spent processing images',
                                      ['operation'])
watermark_success_rate = Counter('watermark_success_total', 'Successful watermark operations', ['operation'])
watermark_error_rate = Counter('watermark_error_total', 'Failed watermark operations', ['operation', 'error_type'])

# Instantiate the Blockchain with optimized difficulty
blockchain = Blockchain(difficulty=3)  # Reduced difficulty for faster mining
node_address = str(uuid4()).replace('-', '')

# Channel layer for real-time updates
channel_layer = get_channel_layer()


def notify_blockchain_update(message, data=None):
    """Send real-time blockchain updates via WebSocket"""
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            'blockchain_updates',
            {
                'type': 'blockchain_update',
                'message': message,
                'data': data or {}
            }
        )


def notify_mining_update(message, data=None):
    """Send real-time mining updates via WebSocket"""
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            'mining_updates',
            {
                'type': 'mining_update',
                'message': message,
                'data': data or {}
            }
        )


# Background mining thread
mining_lock = threading.Lock()


def async_mine_block():
    """Asynchronous mining function"""
    with mining_lock:
        if blockchain.transactions:
            start_time = time.time()

            # Update metrics BEFORE mining starts to capture pending transactions
            pending_count = len(blockchain.transactions)
            pending_transactions.set(pending_count)
            blockchain_operations.labels(operation_type='mine_start').inc()

            # Record in Redis TimeSeries for advanced querying
            blockchain_metrics.record_pending_transactions(pending_count)
            blockchain_metrics.record_operation('mine_start')

            try:
                block = blockchain.batch_mine_pending_transactions()
                if block:
                    duration = time.time() - start_time

                    # Update Prometheus metrics
                    mining_duration.observe(duration)
                    blockchain_operations.labels(operation_type='mine_success').inc()
                    blockchain_length.set(len(blockchain.chain))
                    pending_transactions.set(len(blockchain.transactions))

                    # Record in Redis TimeSeries
                    blockchain_metrics.record_mining_duration(duration)
                    blockchain_metrics.record_blockchain_length(len(blockchain.chain))
                    blockchain_metrics.record_pending_transactions(len(blockchain.transactions))
                    blockchain_metrics.record_operation('mine_success')

                    # Notify about successful mining
                    notify_blockchain_update(f'Async Block {block["index"]} successfully mined!')
                else:
                    blockchain_operations.labels(operation_type='mine_failure').inc()
                    blockchain_metrics.record_operation('mine_failure')
                    pending_transactions.set(len(blockchain.transactions))
            except Exception as e:
                blockchain_operations.labels(operation_type='mine_failure').inc()
                blockchain_metrics.record_operation('mine_failure')
                pending_transactions.set(len(blockchain.transactions))
                print(f"Mining error: {e}")


# Add imports for QR code reading
from PIL import Image as PILImage
from pyzbar.pyzbar import decode

def watermark(request):
    if request.method == 'POST':
        image = request.FILES.get('image')
        qr_code_file = request.FILES.get('qr_code')  # Expecting a file input named 'qr_code'

        if not image_file:
            return JsonResponse({'error': 'No image file provided.'}, status=400)
        if not secret_message:
            return JsonResponse({'error': 'Secret message cannot be empty.'}, status=400)

        # Save the uploaded image to disk first
        original_filename = f'original_{uuid.uuid4()}_{image_file.name}'
        original_path = os.path.join(settings.MEDIA_ROOT, 'images', original_filename)
        os.makedirs(os.path.dirname(original_path), exist_ok=True)
        with open(original_path, 'wb+') as destination:
            for chunk in image_file.chunks():
                destination.write(chunk)

        # Save the uploaded QR code image to disk
        qr_filename = f'qr_{uuid.uuid4()}_{qr_code_file.name}'
        qr_path = os.path.join(settings.MEDIA_ROOT, 'qr_codes', qr_filename)
        os.makedirs(os.path.dirname(qr_path), exist_ok=True)
        with open(qr_path, 'wb+') as destination:
            for chunk in qr_code_file.chunks():
                destination.write(chunk)

        # Extract text from the QR code image
        qr_img = PILImage.open(qr_path)
        decoded_objs = decode(qr_img)
        if not decoded_objs:
            return render(request, 'converter/watermark.html', {'error': 'Could not decode QR code.'})
        secret_message = decoded_objs[0].data.decode('utf-8')

        # Use the saved file path for watermarking
        watermarked_image = lsb.hide(original_path, secret_message, auto_convert_rgb=True)
        watermarked_filename = f'watermarked_{uuid.uuid4()}.png'
        watermarked_path = os.path.join(settings.MEDIA_ROOT, 'watermarked_images', watermarked_filename)
        os.makedirs(os.path.dirname(watermarked_path), exist_ok=True)
        watermarked_image.save(watermarked_path)

        # Save both images to the model
        img = Image(secret_message=secret_message)
        with open(original_path, 'rb') as f:
            img.image.save(original_filename, File(f), save=False)
        with open(watermarked_path, 'rb') as f:
            img.watermarked_image.save(watermarked_filename, File(f), save=False)
        img.save()

        # Add transaction to blockchain (batch processing) with watermark metadata
        import hashlib

        # Create meaningful metadata for the watermarked image
        image_hash = hashlib.sha256(open(original_path, 'rb').read()).hexdigest()
        message_hash = hashlib.sha256(secret_message.encode()).hexdigest()

        watermark_metadata = {
            'image_hash': image_hash,
            'message_hash': message_hash,
            'created_at': str(img.id),
            'file_size': os.path.getsize(watermarked_path)
        }

        blockchain.add_transaction(
            sender=node_address,
            receiver=str(img.id),
            amount=1,
            metadata=watermark_metadata
        )

        # Notify about new watermark transaction
        notify_blockchain_update(f'New watermarked image: {str(img.id)[:8]} | Hash: {image_hash[:16]}')

        # Start async mining if there are pending transactions
        if len(blockchain.transactions) >= 1:  # Mine when we have at least 1 transaction
            threading.Thread(target=async_mine_block, daemon=True).start()

            # Wait briefly for mining to complete
            time.sleep(0.1)

            # Update image with blockchain data if block was mined
            if blockchain.chain:
                latest_block = blockchain.get_previous_block()
                img.block_index = latest_block['index']
                img.blockchain_hash = blockchain.hash(latest_block)
                img.save()

                # Notify about successful blockchain integration
                notify_blockchain_update(f'Image {str(img.id)[:8]} linked to block {latest_block["index"]}')

        # Update Prometheus metrics
        watermark_operations.labels(operation_type='encode').inc()
        blockchain_operations.labels(operation_type='add_transaction').inc()
        pending_transactions.set(len(blockchain.transactions))
        blockchain_length.set(len(blockchain.chain))

        context = {
            'watermarkedImage': img.watermarked_image.url,
            'image': img.image.url,
        }

        return render(request, 'converter/watermark_success.html', context)

    return render(request, 'converter/watermark.html')


def reveal_watermark(request):
    if request.method == 'POST':
        image = request.FILES.get('image')
        if image:
            # Reveal the watermark
            revealed_message = lsb.reveal(image)
            print(f"Revealed message: {revealed_message}")
            return render(request, 'converter/reveal_watermark.html', {'revealed_message': revealed_message})
    return render(request, 'converter/reveal_watermark.html', {'revealed_message': None})


def blockchain_view(request):
    # Update metrics when viewing blockchain page
    blockchain_length.set(len(blockchain.chain))
    pending_transactions.set(len(blockchain.transactions))

    # Ensure we're passing clean data to avoid template variable conflicts
    chain_data = []
    for block in blockchain.chain:
        block_data = {
            'index': block.get('index', 0),
            'timestamp': block.get('timestamp', ''),
            'proof': block.get('proof', 0),
            'previous_hash': block.get('previous_hash', ''),
            'transactions': block.get('transactions', [])
        }
        chain_data.append(block_data)

    context = {
        'chain': chain_data,
        'length': len(blockchain.chain),
        'blockchain_stats': {
            'total_blocks': len(blockchain.chain),
            'pending_transactions': len(blockchain.transactions)
        }
    }
    return render(request, 'converter/blockchain.html', context)


# Unified blockchain stats endpoint (handles both sync and async requests)
def async_blockchain_stats(request):
    """Unified endpoint for blockchain statistics (handles both sync and async requests)"""
    stats = {
        'chain_length': len(blockchain.chain),
        'pending_transactions': len(blockchain.transactions),
        'difficulty': blockchain.difficulty,
        'latest_block_hash': blockchain.hash(blockchain.get_previous_block()) if blockchain.chain else None,
        'mining_status': 'active' if blockchain.transactions else 'idle',
        'timestamp': time.time()
    }
    return JsonResponse(stats)


# Async mining endpoint
@csrf_exempt
def async_mine_block_endpoint(request):
    """Async mining endpoint that doesn't block the request"""
    if request.method == 'POST':
        # Trigger async mining via WebSocket
        notify_mining_update('Async mining requested...')

        # Start mining in background
        threading.Thread(target=async_mine_block, daemon=True).start()

        return JsonResponse({
            'status': 'mining_started',
            'message': 'Mining process initiated asynchronously',
            'timestamp': time.time()
        })

    return JsonResponse({'error': 'Only POST method allowed'}, status=405)


# Endpoint to expose Prometheus metrics
def metrics(request):
    """Expose metrics for Prometheus"""
    return HttpResponse(generate_latest(), content_type="text/plain; charset=utf-8")


# Stress Testing Endpoints
@csrf_exempt
def stress_test_mining(request):
    """Stress test endpoint for mining operations"""
    if request.method == 'POST':
        num_blocks = int(request.POST.get('num_blocks', 10))
        concurrent_threads = int(request.POST.get('concurrent_threads', 5))

        def stress_mine():
            for i in range(num_blocks // concurrent_threads):
                # Add a transaction and IMMEDIATELY capture the pending count
                blockchain.add_transaction(
                    sender=f"stress_test_{uuid4().hex[:8]}",
                    receiver=f"target_{uuid4().hex[:8]}",
                    amount=1
                )
                # Update pending transactions metric RIGHT AFTER adding transaction
                pending_transactions.set(len(blockchain.transactions))

                # Small delay to allow Prometheus to capture the spike
                time.sleep(0.05)

                threading.Thread(target=async_mine_block, daemon=True).start()
                time.sleep(0.1)  # Small delay to prevent overwhelming

        # Start multiple concurrent mining threads
        for _ in range(concurrent_threads):
            threading.Thread(target=stress_mine, daemon=True).start()

        return JsonResponse({
            'status': 'stress_test_started',
            'blocks_to_mine': num_blocks,
            'concurrent_threads': concurrent_threads,
            'message': f'Started stress test: {num_blocks} blocks with {concurrent_threads} threads'
        })

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def stress_test_watermarking(request):
    """Stress test endpoint for watermarking operations"""
    if request.method == 'POST':
        num_operations = int(request.POST.get('num_operations', 20))

        def create_test_watermark(i):
            try:
                # Create a simple test image
                from PIL import Image as PILImage
                import io

                # Create a simple test image
                test_image = PILImage.new('RGB', (100, 100), color='red')
                img_buffer = io.BytesIO()
                test_image.save(img_buffer, format='PNG')
                img_buffer.seek(0)

                # Save test image
                test_filename = f'stress_test_{uuid4().hex[:8]}.png'
                test_path = os.path.join(settings.MEDIA_ROOT, 'images', test_filename)
                os.makedirs(os.path.dirname(test_path), exist_ok=True)

                with open(test_path, 'wb') as f:
                    f.write(img_buffer.getvalue())

                # Create watermark
                secret_message = f"Stress test message {i}"
                watermarked_image = lsb.hide(test_path, secret_message, auto_convert_rgb=True)
                watermarked_filename = f'watermarked_stress_{uuid4().hex[:8]}.png'
                watermarked_path = os.path.join(settings.MEDIA_ROOT, 'watermarked_images', watermarked_filename)
                os.makedirs(os.path.dirname(watermarked_path), exist_ok=True)
                watermarked_image.save(watermarked_path)

                # Update metrics
                watermark_operations.labels(operation_type='stress_test').inc()

                # Add to blockchain
                import hashlib
                image_hash = hashlib.sha256(open(test_path, 'rb').read()).hexdigest()
                message_hash = hashlib.sha256(secret_message.encode()).hexdigest()

                watermark_metadata = {
                    'image_hash': image_hash,
                    'message_hash': message_hash,
                    'created_at': f'stress_test_{i}',
                    'file_size': os.path.getsize(watermarked_path)
                }

                blockchain.add_transaction(
                    sender=f"stress_test_{uuid4().hex[:8]}",
                    receiver=f"watermark_{i}",
                    amount=1,
                    metadata=watermark_metadata
                )

                blockchain_operations.labels(operation_type='stress_add_transaction').inc()

            except Exception as e:
                watermark_error_rate.labels(operation='stress_test', error_type='processing_error').inc()
                print(f"Stress test error {i}: {e}")

        # Create watermarks concurrently
        for i in range(num_operations):
            threading.Thread(target=create_test_watermark, args=(i,), daemon=True).start()
            time.sleep(0.05)  # Small delay to prevent overwhelming

        return JsonResponse({
            'status': 'watermark_stress_test_started',
            'operations': num_operations,
            'message': f'Started watermarking stress test: {num_operations} operations'
        })

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def stress_test_combined(request):
    """Combined stress test for both mining and watermarking"""
    if request.method == 'POST':
        watermark_ops = int(request.POST.get('watermark_ops', 15))
        mining_blocks = int(request.POST.get('mining_blocks', 10))
        duration_seconds = int(request.POST.get('duration', 60))

        start_time = time.time()

        def combined_stress_worker():
            worker_id = uuid4().hex[:8]
            operations = 0

            while time.time() - start_time < duration_seconds:
                try:
                    # Add multiple transactions in batches to create pending spikes
                    if operations % 3 == 0:
                        # Add multiple transactions quickly to create a backlog
                        for batch in range(3):
                            blockchain.add_transaction(
                                sender=f"combined_stress_{worker_id}",
                                receiver=f"target_{operations}_{batch}",
                                amount=1,
                                metadata={
                                    'stress_test': True,
                                    'worker_id': worker_id,
                                    'operation': operations,
                                    'batch': batch
                                }
                            )
                        # Update pending count AFTER adding multiple transactions
                        pending_transactions.set(len(blockchain.transactions))
                        watermark_operations.labels(operation_type='combined_stress').inc()

                        # Small delay to allow Prometheus to capture the spike
                        time.sleep(0.1)
                    else:
                        # Trigger mining
                        threading.Thread(target=async_mine_block, daemon=True).start()

                    operations += 1
                    blockchain_operations.labels(operation_type='combined_stress').inc()
                    time.sleep(0.3)  # Slower pace to allow pending transactions to accumulate

                except Exception as e:
                    watermark_error_rate.labels(operation='combined_stress', error_type='worker_error').inc()
                    print(f"Combined stress worker {worker_id} error: {e}")

        # Start multiple workers
        num_workers = 2  # Reduced workers to allow more pending accumulation
        for _ in range(num_workers):
            threading.Thread(target=combined_stress_worker, daemon=True).start()

        return JsonResponse({
            'status': 'combined_stress_test_started',
            'duration_seconds': duration_seconds,
            'workers': num_workers,
            'watermark_ops_target': watermark_ops,
            'mining_blocks_target': mining_blocks,
            'message': f'Started combined stress test for {duration_seconds} seconds with {num_workers} workers'
        })

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def stress_test_pending_transactions(request):
    """Special stress test designed to create visible pending transaction spikes"""
    if request.method == 'POST':
        batch_size = int(request.POST.get('batch_size', 10))
        num_batches = int(request.POST.get('num_batches', 5))

        def create_pending_spike():
            for batch_num in range(num_batches):
                # Add multiple transactions rapidly
                for i in range(batch_size):
                    blockchain.add_transaction(
                        sender=f"pending_test_{uuid4().hex[:8]}",
                        receiver=f"batch_{batch_num}_tx_{i}",
                        amount=1
                    )

                # Update pending count after adding the batch
                current_pending = len(blockchain.transactions)
                pending_transactions.set(current_pending)
                print(f"Created pending spike: {current_pending} transactions")

                # Wait longer to allow Prometheus to capture the spike
                time.sleep(1.0)

                # Then start mining to process some transactions
                for _ in range(2):  # Start 2 mining threads
                    threading.Thread(target=async_mine_block, daemon=True).start()

                # Wait before next batch
                time.sleep(2.0)

        # Start the pending spike creator
        threading.Thread(target=create_pending_spike, daemon=True).start()

        return JsonResponse({
            'status': 'pending_spike_test_started',
            'batch_size': batch_size,
            'num_batches': num_batches,
            'message': f'Started pending transaction spike test: {num_batches} batches of {batch_size} transactions'
        })

    return JsonResponse({'error': 'Invalid request method'}, status=405)
