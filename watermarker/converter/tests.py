import copy
import hashlib
import json
import os
import tempfile
import time

from PIL import Image as PILImage
from channels.testing import WebsocketCommunicator
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from converter.blockchain import Blockchain
from .consumers import BlockchainConsumer, MiningConsumer
from .models import Image


class BlockchainTestCase(TestCase):
    """Test suite for the Blockchain core functionality"""

    def setUp(self):
        self.blockchain = Blockchain(difficulty=2)  # Lower difficulty for faster tests

    def test_blockchain_initialization(self):
        """Test blockchain initializes with genesis block"""
        self.assertEqual(len(self.blockchain.chain), 1)
        self.assertEqual(self.blockchain.chain[0]['index'], 1)
        self.assertEqual(self.blockchain.chain[0]['previous_hash'], '0')

    def test_create_block(self):
        """Test block creation functionality"""
        initial_length = len(self.blockchain.chain)

        # Add a transaction
        self.blockchain.add_transaction('sender', 'receiver', 10)

        # Create a new block
        previous_block = self.blockchain.get_previous_block()
        proof = self.blockchain.proof_of_work(previous_block['proof'])
        previous_hash = self.blockchain.hash(previous_block)

        new_block = self.blockchain.create_block(proof, previous_hash)

        self.assertEqual(len(self.blockchain.chain), initial_length + 1)
        self.assertEqual(new_block['index'], initial_length + 1)
        self.assertEqual(len(new_block['transactions']), 1)

    def test_proof_of_work(self):
        """Test proof of work algorithm"""
        previous_block = self.blockchain.get_previous_block()
        proof = self.blockchain.proof_of_work(previous_block['proof'])

        # Verify the proof
        hash_operation = hashlib.sha256(
            str(proof ** 2 - previous_block['proof'] ** 2).encode()
        ).hexdigest()

        # Check if proof produces the required number of leading zeros
        self.assertTrue(hash_operation.startswith('0' * self.blockchain.difficulty))

    def test_chain_validation(self):
        """Test blockchain validation"""
        # Add some blocks to the chain
        for i in range(3):
            self.blockchain.add_transaction(f'sender{i}', f'receiver{i}', i + 1)
            previous_block = self.blockchain.get_previous_block()
            proof = self.blockchain.proof_of_work(previous_block['proof'])
            previous_hash = self.blockchain.hash(previous_block)
            self.blockchain.create_block(proof, previous_hash)

        self.assertTrue(self.blockchain.is_chain_valid(self.blockchain.chain))

    def test_transaction_addition(self):
        """Test transaction addition to blockchain"""
        initial_tx_count = len(self.blockchain.transactions)

        block_index = self.blockchain.add_transaction('Alice', 'Bob', 50)

        self.assertEqual(len(self.blockchain.transactions), initial_tx_count + 1)
        self.assertEqual(self.blockchain.transactions[-1]['s'], 'Alice')
        self.assertEqual(self.blockchain.transactions[-1]['r'], 'Bob')
        self.assertEqual(self.blockchain.transactions[-1]['a'], 50)

    def test_batch_mining(self):
        """Test batch mining functionality"""
        # Add multiple transactions
        self.blockchain.add_transaction('user1', 'user2', 10)
        self.blockchain.add_transaction('user3', 'user4', 20)

        initial_length = len(self.blockchain.chain)
        block = self.blockchain.batch_mine_pending_transactions()

        self.assertIsNotNone(block)
        self.assertEqual(len(self.blockchain.chain), initial_length + 1)
        self.assertEqual(len(block['transactions']), 2)
        self.assertEqual(len(self.blockchain.transactions), 0)  # Transactions should be cleared


class WatermarkBlockchainIntegrationTestCase(TestCase):
    """Test suite for watermark and blockchain integration"""

    def setUp(self):
        # Create a test image
        self.test_image = self.create_test_image()

    def create_test_image(self):
        """Create a test RGB image"""
        image = PILImage.new('RGB', (100, 100), color='red')
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        image.save(temp_file.name)
        temp_file.close()

        with open(temp_file.name, 'rb') as f:
            uploaded_file = SimpleUploadedFile(
                name='test_image.png',
                content=f.read(),
                content_type='image/png'
            )

        os.unlink(temp_file.name)
        return uploaded_file

    def test_watermark_creation_with_blockchain(self):
        """Test watermark creation integrates with blockchain"""
        response = self.client.post(reverse('watermark'), {
            'image': self.test_image,
            'secret_message': 'Test secret message'
        })

        self.assertEqual(response.status_code, 200)

        # Check if image was created in database
        image = Image.objects.first()
        self.assertIsNotNone(image)
        self.assertEqual(image.secret_message, 'Test secret message')
        self.assertIsNotNone(image.block_index)
        self.assertIsNotNone(image.blockchain_hash)

    def test_blockchain_view_rendering(self):
        """Test blockchain view renders correctly"""
        response = self.client.get(reverse('blockchain'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Blockchain')
        self.assertContains(response, 'ASGI Enabled')
        self.assertContains(response, 'Mining Status')

    def test_mining_endpoint(self):
        """Test manual mining endpoint"""
        response = self.client.post(reverse('mine_block'))

        self.assertEqual(response.status_code, 200)  # API endpoint returns 200
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'mining_started')

    def test_blockchain_stats_api(self):
        """Test blockchain statistics API"""
        response = self.client.get(reverse('blockchain_stats'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertIn('chain_length', data)
        self.assertIn('pending_transactions', data)
        self.assertIn('difficulty', data)

    def test_async_blockchain_stats(self):
        """Test async blockchain statistics endpoint"""
        response = self.client.get(reverse('async_blockchain_stats'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertIn('chain_length', data)
        self.assertIn('mining_status', data)
        self.assertIn('timestamp', data)


class WebSocketTestCase(TransactionTestCase):
    """Test suite for WebSocket functionality"""

    async def test_blockchain_consumer_connection(self):
        """Test blockchain WebSocket consumer connection"""
        communicator = WebsocketCommunicator(BlockchainConsumer.as_asgi(), "/ws/blockchain/")
        connected, subprotocol = await communicator.connect()

        self.assertTrue(connected)

        # Test receiving initial blockchain data
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'blockchain_update')
        self.assertIn('chain', response)
        self.assertIn('length', response)

        await communicator.disconnect()

    async def test_mining_consumer_connection(self):
        """Test mining WebSocket consumer connection"""
        communicator = WebsocketCommunicator(MiningConsumer.as_asgi(), "/ws/mining/")
        connected, subprotocol = await communicator.connect()

        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_blockchain_consumer_stats_request(self):
        """Test requesting stats through blockchain WebSocket"""
        communicator = WebsocketCommunicator(BlockchainConsumer.as_asgi(), "/ws/blockchain/")
        connected, subprotocol = await communicator.connect()

        # Skip initial blockchain update
        await communicator.receive_json_from()

        # Request stats
        await communicator.send_json_to({'type': 'get_stats'})
        response = await communicator.receive_json_from()

        self.assertEqual(response['type'], 'blockchain_stats')
        self.assertIn('chain_length', response)
        self.assertIn('pending_transactions', response)

        await communicator.disconnect()

    async def test_mining_consumer_start_mining(self):
        """Test starting mining through WebSocket"""
        communicator = WebsocketCommunicator(MiningConsumer.as_asgi(), "/ws/mining/")
        connected, subprotocol = await communicator.connect()

        # Start mining
        await communicator.send_json_to({'type': 'start_mining'})

        # Expect mining started message
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'mining_started')

        # Expect mining progress messages
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'mining_progress')

        await communicator.disconnect()


class ModelTestCase(TestCase):
    """Test suite for Django models"""

    def test_image_model_creation(self):
        """Test Image model creation"""
        image = Image.objects.create(
            secret_message='Test message',
            block_index=1,
            blockchain_hash='abc123'
        )

        self.assertEqual(image.secret_message, 'Test message')
        self.assertEqual(image.block_index, 1)
        self.assertEqual(image.blockchain_hash, 'abc123')
        self.assertIsNotNone(image.id)

    def test_image_model_string_representation(self):
        """Test Image model string representation"""
        image = Image.objects.create(secret_message='Test')

        expected_str = f"Image {image.id} - "
        self.assertTrue(str(image).startswith(expected_str))


class PerformanceTestCase(TestCase):
    """Test suite for performance optimization features"""

    def test_blockchain_caching(self):
        """Test blockchain caching functionality"""
        blockchain = Blockchain()

        # First call should cache the result
        previous_block1 = blockchain.get_previous_block()

        # Second call should return cached result
        previous_block2 = blockchain.get_previous_block()

        self.assertEqual(previous_block1, previous_block2)
        self.assertIs(previous_block1, previous_block2)  # Same object reference

    def test_optimized_transaction_format(self):
        """Test optimized transaction format"""
        blockchain = Blockchain()

        # Add transaction with long IDs
        long_sender = 'a' * 20
        long_receiver = 'b' * 20

        blockchain.add_transaction(long_sender, long_receiver, 100)

        transaction = blockchain.transactions[0]

        # Check that IDs are truncated
        self.assertEqual(len(transaction['s']), 8)
        self.assertEqual(len(transaction['r']), 8)
        self.assertEqual(transaction['a'], 100)

    def test_adjustable_difficulty(self):
        """Test adjustable difficulty setting"""
        easy_blockchain = Blockchain(difficulty=1)
        hard_blockchain = Blockchain(difficulty=4)

        self.assertEqual(easy_blockchain.difficulty, 1)
        self.assertEqual(hard_blockchain.difficulty, 4)

        # Easy blockchain should mine faster
        start_time = time.time()
        easy_proof = easy_blockchain.proof_of_work(1)
        easy_time = time.time() - start_time

        # Verify proof meets difficulty requirement
        previous_proof = easy_blockchain.get_previous_block()['proof']
        hash_op = hashlib.sha256(
            str(easy_proof ** 2 - previous_proof ** 2).encode()
        ).hexdigest()
        self.assertTrue(hash_op.startswith('0' * easy_blockchain.difficulty))


class SecurityTestCase(TestCase):
    """Test suite for security features"""

    def test_blockchain_immutability(self):
        """Test that blockchain data cannot be easily tampered with"""
        blockchain = Blockchain()

        # Add some blocks
        for i in range(2):
            blockchain.add_transaction(f'user{i}', f'user{i + 1}', i + 1)
            previous_block = blockchain.get_previous_block()
            proof = blockchain.proof_of_work(previous_block['proof'])
            previous_hash = blockchain.hash(previous_block)
            blockchain.create_block(proof, previous_hash)

        # Store original chain
        original_chain = copy.deepcopy(blockchain.chain)

        # Attempt to tamper with a block
        blockchain.chain[1]['transactions'][0]['a'] = 9999

        # Chain should now be invalid
        self.assertFalse(blockchain.is_chain_valid(blockchain.chain))

        # Restore original chain
        blockchain.chain = original_chain
        self.assertTrue(blockchain.is_chain_valid(blockchain.chain))

    def test_hash_consistency(self):
        """Test that hash function produces consistent results"""
        blockchain = Blockchain()

        test_block = {
            'index': 1,
            'timestamp': '2025-08-03 21:00:00',
            'proof': 123,
            'previous_hash': '0',
            'transactions': []
        }

        hash1 = blockchain.hash(test_block)
        hash2 = blockchain.hash(test_block)

        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)  # SHA-256 produces 64-character hex string


class LifecyclePipelineTestCase(TestCase):
    """Test suite for complete watermark-blockchain lifecycle pipeline"""

    def setUp(self):
        self.test_image = self.create_test_image()

    def create_test_image(self):
        """Create a test RGB image"""
        image = PILImage.new('RGB', (100, 100), color='blue')
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        image.save(temp_file.name)
        temp_file.close()

        with open(temp_file.name, 'rb') as f:
            uploaded_file = SimpleUploadedFile(
                name='lifecycle_test.png',
                content=f.read(),
                content_type='image/png'
            )

        os.unlink(temp_file.name)
        return uploaded_file

    def test_complete_watermark_lifecycle(self):
        """Test full pipeline: upload → watermark → mine → verify → retrieve"""
        # Step 1: Upload and watermark image
        secret_message = 'Lifecycle test message'
        response = self.client.post(reverse('watermark'), {
            'image': self.test_image,
            'secret_message': secret_message
        })

        self.assertEqual(response.status_code, 200)

        # Step 2: Verify database record
        image_record = Image.objects.first()
        self.assertIsNotNone(image_record)
        self.assertEqual(image_record.secret_message, secret_message)

        # Step 3: Verify blockchain integration
        self.assertIsNotNone(image_record.block_index)
        self.assertIsNotNone(image_record.blockchain_hash)

        # Step 4: Verify watermarked image exists
        self.assertTrue(image_record.watermarked_image)
        self.assertTrue(os.path.exists(image_record.watermarked_image.path))

        # Step 5: Test watermark reveal
        with open(image_record.watermarked_image.path, 'rb') as f:
            reveal_response = self.client.post(reverse('reveal_watermark'), {
                'image': SimpleUploadedFile('test_reveal.png', f.read())
            })

        self.assertEqual(reveal_response.status_code, 200)
        self.assertContains(reveal_response, secret_message)

    def test_watermark_metadata_blockchain_integration(self):
        """Test watermark metadata properly stored in blockchain"""
        from converter.views import blockchain
        import hashlib

        # Upload watermarked image
        secret_message = 'Metadata test'
        response = self.client.post(reverse('watermark'), {
            'image': self.test_image,
            'secret_message': secret_message
        })

        # Check blockchain contains watermark metadata
        latest_block = blockchain.get_previous_block()
        transactions = latest_block.get('transactions', [])

        watermark_tx = None
        for tx in transactions:
            if tx.get('type') == 'watermark':
                watermark_tx = tx
                break

        self.assertIsNotNone(watermark_tx, "No watermark transaction found in blockchain")
        self.assertIn('img_hash', watermark_tx)
        self.assertIn('msg_hash', watermark_tx)
        self.assertIn('size', watermark_tx)
        self.assertEqual(watermark_tx['type'], 'watermark')

        # Verify message hash matches
        expected_msg_hash = hashlib.sha256(secret_message.encode()).hexdigest()[:16]
        self.assertEqual(watermark_tx['msg_hash'], expected_msg_hash)

    def test_multiple_watermarks_blockchain_sequence(self):
        """Test multiple watermarks create proper blockchain sequence"""
        from converter.views import blockchain

        initial_chain_length = len(blockchain.chain)

        # Create multiple watermarked images
        for i in range(3):
            test_image = self.create_test_image()
            response = self.client.post(reverse('watermark'), {
                'image': test_image,
                'secret_message': f'Test message {i}'
            })
            self.assertEqual(response.status_code, 200)

        # Verify blockchain grew
        final_chain_length = len(blockchain.chain)
        self.assertGreater(final_chain_length, initial_chain_length)

        # Verify all images are in database with blockchain links
        images = Image.objects.all()
        for img in images:
            self.assertIsNotNone(img.block_index)
            self.assertIsNotNone(img.blockchain_hash)

    def test_watermarked_image_integrity(self):
        """Test watermarked images maintain file integrity"""
        secret_message = 'Integrity test'
        response = self.client.post(reverse('watermark'), {
            'image': self.test_image,
            'secret_message': secret_message
        })

        image_record = Image.objects.first()

        # Verify files exist and are readable
        self.assertTrue(os.path.exists(image_record.image.path))
        self.assertTrue(os.path.exists(image_record.watermarked_image.path))

        # Verify file sizes are reasonable
        original_size = os.path.getsize(image_record.image.path)
        watermarked_size = os.path.getsize(image_record.watermarked_image.path)

        self.assertGreater(original_size, 0)
        self.assertGreater(watermarked_size, 0)

        # Watermarked image should be similar size (within 25% difference)
        size_difference = abs(watermarked_size - original_size) / original_size
        self.assertLess(size_difference, 0.25, "Watermarked image size differs too much from original")


class ASGIIntegrationTestCase(TransactionTestCase):
    """Test suite for ASGI and real-time features"""

    def test_concurrent_watermark_operations(self):
        """Test multiple simultaneous watermarking operations"""
        import threading
        import queue

        results = queue.Queue()

        def watermark_operation(thread_id):
            try:
                # Create unique test image for each thread
                image = PILImage.new('RGB', (50, 50), color=(thread_id * 50, 100, 150))
                temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                image.save(temp_file.name)
                temp_file.close()

                with open(temp_file.name, 'rb') as f:
                    test_image = SimpleUploadedFile(
                        f'concurrent_test_{thread_id}.png',
                        f.read(),
                        content_type='image/png'
                    )

                # Perform watermarking
                response = self.client.post(reverse('watermark'), {
                    'image': test_image,
                    'secret_message': f'Concurrent test {thread_id}'
                })

                results.put(('success', thread_id, response.status_code))
                os.unlink(temp_file.name)

            except Exception as e:
                results.put(('error', thread_id, str(e)))

        # Start multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=watermark_operation, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check results
        success_count = 0
        while not results.empty():
            result_type, thread_id, result = results.get()
            if result_type == 'success':
                self.assertEqual(result, 200)
                success_count += 1

        self.assertEqual(success_count, 3, "Not all concurrent operations succeeded")

    async def test_websocket_blockchain_real_time_updates(self):
        """Test real-time blockchain updates via WebSocket"""
        from converter.views import blockchain

        # Connect to blockchain WebSocket
        communicator = WebsocketCommunicator(BlockchainConsumer.as_asgi(), "/ws/blockchain/")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Skip initial blockchain update
        await communicator.receive_json_from()

        # Trigger a blockchain update by adding a transaction
        initial_length = len(blockchain.chain)
        blockchain.add_transaction('test_sender', 'test_receiver', 1)

        # Mine the block
        previous_block = blockchain.get_previous_block()
        proof = blockchain.proof_of_work(previous_block['proof'])
        previous_hash = blockchain.hash(previous_block)
        new_block = blockchain.create_block(proof, previous_hash)

        # Request updated blockchain data
        await communicator.send_json_to({'type': 'get_blockchain'})
        response = await communicator.receive_json_from()

        # Verify real-time update
        self.assertEqual(response['type'], 'blockchain_update')
        self.assertEqual(response['length'], initial_length + 1)
        self.assertIn('chain', response)

        await communicator.disconnect()


class ErrorHandlingTestCase(TestCase):
    """Test suite for error handling and edge cases"""

    def test_invalid_image_format(self):
        """Test handling of invalid image formats"""
        # Create a text file pretending to be an image
        invalid_file = SimpleUploadedFile(
            'invalid.txt',
            b'This is not an image',
            content_type='text/plain'
        )

        response = self.client.post(reverse('watermark'), {
            'image': invalid_file,
            'secret_message': 'Test message'
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Invalid or corrupted image file.')

    def test_empty_secret_message(self):
        """Test watermarking with empty secret message"""
        test_image = self.create_test_image()

        response = self.client.post(reverse('watermark'), {
            'image': test_image,
            'secret_message': ''
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Secret message cannot be empty.')

    def test_blockchain_integrity_after_errors(self):
        """Test blockchain maintains integrity after error conditions"""
        from converter.views import blockchain

        initial_chain = blockchain.chain.copy()
        initial_valid = blockchain.is_chain_valid(blockchain.chain)

        try:
            # Try to cause an error condition
            blockchain.add_transaction(None, None, None)
        except:
            pass

        # Blockchain should still be valid
        final_valid = blockchain.is_chain_valid(blockchain.chain)
        self.assertTrue(initial_valid)
        self.assertTrue(final_valid)

    def create_test_image(self):
        """Helper method to create test images"""
        image = PILImage.new('RGB', (100, 100), color='red')
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        image.save(temp_file.name)
        temp_file.close()

        with open(temp_file.name, 'rb') as f:
            uploaded_file = SimpleUploadedFile(
                name='test_image.png',
                content=f.read(),
                content_type='image/png'
            )

        os.unlink(temp_file.name)
        return uploaded_file
