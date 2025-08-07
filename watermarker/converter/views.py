from django.shortcuts import render
from django.conf import settings
from stegano import lsb
from .models import Image
import os, uuid
from django.core.files import File

# Add imports for QR code reading
from PIL import Image as PILImage
from pyzbar.pyzbar import decode

def watermark(request):
    if request.method == 'POST':
        image = request.FILES.get('image')
        qr_code_file = request.FILES.get('qr_code')  # Expecting a file input named 'qr_code'

        # Save the uploaded image to disk first
        original_filename = f'original_{uuid.uuid4()}_{image.name}'
        original_path = os.path.join(settings.MEDIA_ROOT, 'images', original_filename)
        os.makedirs(os.path.dirname(original_path), exist_ok=True)
        with open(original_path, 'wb+') as destination:
            for chunk in image.chunks():
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