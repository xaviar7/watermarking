from django.db import models
import uuid

class Image(models.Model):
    image = models.ImageField(upload_to='images/')
    watermarked_image = models.ImageField(upload_to='watermarked_images/', blank=True, null=True)
    secret_message = models.TextField(blank=True, null=True)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    def __str__(self):
        return f"Image {self.id} - {self.image.name}"