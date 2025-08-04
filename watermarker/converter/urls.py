from django.urls import path

from .views import (
    watermark, reveal_watermark, blockchain_view,
    async_blockchain_stats, async_mine_block_endpoint, metrics,
    stress_test_mining, stress_test_watermarking, stress_test_combined,
    stress_test_pending_transactions
)

urlpatterns = [
    path('', watermark, name='watermark'),
    path('reveal/', reveal_watermark, name='reveal_watermark'),
    path('blockchain/', blockchain_view, name='blockchain'),

    # Use async endpoints only
    path('blockchain/stats/', async_blockchain_stats, name='blockchain_stats'),
    path('blockchain/async-stats/', async_blockchain_stats, name='async_blockchain_stats'),
    # Keep both for compatibility
    path('mine_block/', async_mine_block_endpoint, name='mine_block'),  # Now fully async
    path('blockchain/async-mine/', async_mine_block_endpoint, name='async_mine_block'),
    path('metrics/', metrics, name='metrics'),

    # Stress Testing Endpoints
    path('stress-test/mining/', stress_test_mining, name='stress_test_mining'),
    path('stress-test/watermarking/', stress_test_watermarking, name='stress_test_watermarking'),
    path('stress-test/combined/', stress_test_combined, name='stress_test_combined'),
    path('stress-test/pending/', stress_test_pending_transactions, name='stress_test_pending_transactions'),
]
