from django.shortcuts import render
from django.conf import settings
from stegano import lsb
from .models import Image
import os, uuid
from django.core.files import File

def watermark(request):
    if request.method == 'POST':
        image = request.FILES.get('image')
        secret_message = request.POST.get('secret_message')

        # Save the uploaded image to disk first
        original_filename = f'original_{uuid.uuid4()}_{image.name}'
        original_path = os.path.join(settings.MEDIA_ROOT, 'images', original_filename)
        os.makedirs(os.path.dirname(original_path), exist_ok=True)
        with open(original_path, 'wb+') as destination:
            for chunk in image.chunks():
                destination.write(chunk)

        # Use the saved file path for watermarking
        watermarked_image = lsb.hide(original_path, secret_message)
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
  return render(request, 'converter/reveal_watermark.html')