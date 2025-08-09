import uuid

from django.db import models


class Image(models.Model):
    image = models.ImageField(upload_to='images/')
    watermarked_image = models.ImageField(upload_to='watermarked_images/', blank=True, null=True)
    secret_message = models.TextField(blank=True, null=True)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    block_index = models.IntegerField(blank=True, null=True, db_index=True)
    blockchain_hash = models.CharField(max_length=64, blank=True, null=True, db_index=True)

    def __str__(self):
        return f"Image {self.id} - {self.image.name}"

    class Meta:
        indexes = [
            models.Index(fields=['block_index']),
            models.Index(fields=['blockchain_hash']),
        ]
