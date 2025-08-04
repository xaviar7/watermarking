import json
import time

from channels.generic.websocket import AsyncWebsocketConsumer


class BlockchainConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.room_group_name = None

    async def connect(self):
        self.room_group_name = 'blockchain_updates'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Send initial blockchain data
        await self.send_blockchain_update()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'get_blockchain':
                await self.send_blockchain_update()
            elif message_type == 'get_stats':
                await self.send_blockchain_stats()
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON data'
            }))

    async def send_blockchain_update(self):
        """Send current blockchain data to WebSocket"""
        try:
            # Import here to avoid circular imports
            from converter.views import blockchain

            await self.send(text_data=json.dumps({
                'type': 'blockchain_update',
                'chain': blockchain.chain,
                'length': len(blockchain.chain),
                'timestamp': time.time()
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Failed to get blockchain data: {str(e)}'
            }))

    async def send_blockchain_stats(self):
        """Send blockchain statistics"""
        try:
            from converter.views import blockchain

            await self.send(text_data=json.dumps({
                'type': 'blockchain_stats',
                'chain_length': len(blockchain.chain),
                'pending_transactions': len(blockchain.transactions),
                'difficulty': blockchain.difficulty,
                'timestamp': time.time()
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Failed to get stats: {str(e)}'
            }))

    # Receive message from room group
    async def blockchain_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'blockchain_update',
            'message': event['message'],
            'data': event.get('data', {})
        }))


class MiningConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'mining_updates'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'start_mining':
                await self.start_async_mining()
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON data'
            }))

    async def start_async_mining(self):
        """Start asynchronous mining process"""
        try:
            from converter.views import blockchain, node_address

            # Send mining started notification
            await self.send(text_data=json.dumps({
                'type': 'mining_started',
                'message': 'Mining process initiated...',
                'timestamp': time.time()
            }))

            # Perform mining in background
            await self.perform_mining()
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'mining_error',
                'message': f'Mining startup failed: {str(e)}',
                'timestamp': time.time()
            }))

    async def perform_mining(self):
        """Perform actual mining operation"""
        try:
            from converter.views import blockchain, node_address, async_mine_block
            import threading

            # Add a transaction if none exist
            if not blockchain.transactions:
                blockchain.add_transaction(sender=node_address, receiver='WebSocket', amount=1)

            # Send progress update
            await self.send(text_data=json.dumps({
                'type': 'mining_progress',
                'message': f'Mining block with {len(blockchain.transactions)} transactions...',
                'pending_transactions': len(blockchain.transactions),
                'timestamp': time.time()
            }))

            # Start mining in background thread
            def mine_and_notify():
                try:
                    # Call the actual mining function
                    async_mine_block()

                    # Send completion notification via WebSocket
                    import asyncio
                    from channels.layers import get_channel_layer
                    from asgiref.sync import async_to_sync

                    channel_layer = get_channel_layer()
                    if channel_layer:
                        async_to_sync(channel_layer.group_send)(
                            'mining_updates',
                            {
                                'type': 'mining_complete',
                                'message': f'Block successfully mined! Chain length: {len(blockchain.chain)}',
                                'chain_length': len(blockchain.chain),
                                'pending_transactions': len(blockchain.transactions)
                            }
                        )
                except Exception as e:
                    # Send error notification
                    async_to_sync(channel_layer.group_send)(
                        'mining_updates',
                        {
                            'type': 'mining_error',
                            'message': f'Mining failed: {str(e)}'
                        }
                    )

            # Start mining in background
            threading.Thread(target=mine_and_notify, daemon=True).start()

        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'mining_error',
                'message': f'Mining failed: {str(e)}',
                'timestamp': time.time()
            }))

    # Receive message from room group
    async def mining_update(self, event):
        await self.send(text_data=json.dumps(event))

    async def mining_complete(self, event):
        await self.send(text_data=json.dumps(event))

    async def mining_error(self, event):
        await self.send(text_data=json.dumps(event))
