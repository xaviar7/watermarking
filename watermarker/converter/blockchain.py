import datetime
import hashlib
import json
from urllib.parse import urlparse

import requests


class Blockchain:

    def __init__(self, difficulty=4):
        self.chain = []
        self.transactions = []
        self.difficulty = difficulty  # Adjustable difficulty
        self.create_block(proof=1, previous_hash='0')
        self.nodes = set()
        self._cached_previous_block = None
        self._cached_previous_hash = None

    def create_block(self, proof, previous_hash):
        block = {'index': len(self.chain) + 1,
                 'timestamp': str(datetime.datetime.now()),
                 'proof': proof,
                 'previous_hash': previous_hash,
                 'transactions': self.transactions}
        self.transactions = []
        self.chain.append(block)
        # Clear cache when new block is added
        self._cached_previous_block = None
        self._cached_previous_hash = None
        return block

    def get_previous_block(self):
        if self._cached_previous_block is None:
            self._cached_previous_block = self.chain[-1]
        return self._cached_previous_block

    def get_previous_hash_cached(self):
        if self._cached_previous_hash is None:
            self._cached_previous_hash = self.hash(self.get_previous_block())
        return self._cached_previous_hash

    def proof_of_work(self, previous_proof):
        new_proof = 1
        check_proof = False
        target = '0' * self.difficulty  # Use adjustable difficulty
        while not check_proof:
            hash_operation = hashlib.sha256(
                str(new_proof ** 2 - previous_proof ** 2).encode()).hexdigest()
            if hash_operation[:self.difficulty] == target:
                check_proof = True
            else:
                new_proof += 1
        return new_proof

    def hash(self, block):
        encoded_block = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(encoded_block).hexdigest()

    def is_chain_valid(self, chain):
        previous_block = chain[0]
        block_index = 1
        target = '0' * self.difficulty
        while block_index < len(chain):
            block = chain[block_index]
            if block['previous_hash'] != self.hash(previous_block):
                return False
            previous_proof = previous_block['proof']
            proof = block['proof']
            hash_operation = hashlib.sha256(
                str(proof ** 2 - previous_proof ** 2).encode()).hexdigest()
            if hash_operation[:self.difficulty] != target:
                return False
            previous_block = block
            block_index += 1
        return True

    def add_transaction(self, sender, receiver, amount, metadata=None):
        # Optimize transaction data size with image metadata
        transaction = {
            's': sender[:8] if len(sender) > 8 else sender,  # Truncate sender ID
            'r': receiver[:8] if len(receiver) > 8 else receiver,  # Truncate receiver ID
            'a': amount,
            'type': 'watermark' if metadata else 'mining',
        }

        # Add watermark-specific metadata
        if metadata:
            transaction.update({
                'img_hash': metadata.get('image_hash', '')[:16],  # Truncated image hash
                'msg_hash': metadata.get('message_hash', '')[:16],  # Truncated message hash
                'timestamp': metadata.get('created_at', ''),
                'size': metadata.get('file_size', 0)
            })

        self.transactions.append(transaction)
        previous_block = self.get_previous_block()
        return previous_block['index'] + 1

    def batch_mine_pending_transactions(self):
        """Mine all pending transactions in a single block"""
        if not self.transactions:
            return None

        previous_block = self.get_previous_block()
        previous_proof = previous_block['proof']
        proof = self.proof_of_work(previous_proof)
        previous_hash = self.get_previous_hash_cached()

        return self.create_block(proof, previous_hash)

    def add_node(self, address):
        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def replace_chain(self):
        network = self.nodes
        longest_chain = None
        max_length = len(self.chain)
        for node in network:
            response = requests.get(f'http://{node}/get_chain')
            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']
                if length > max_length and self.is_chain_valid(chain):
                    max_length = length
                    longest_chain = chain
        if longest_chain:
            self.chain = longest_chain
            return True
        return False
