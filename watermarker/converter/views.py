from django.shortcuts import render, redirect
from django.http import FileResponse
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.conf import settings
from stegano import lsb
from .models import Image
import os

def send_email(email, subject, message, file_path):
    """
    Sends a simple email using Django's EmailMessage class.
    """
    email_message = EmailMessage(
        subject=subject,
        body=message,
        from_email=settings.EMAIL_HOST_USER,
        to=[email],
    )
    with open(file_path, 'rb') as f:
        email_message.attach(os.path.basename(file_path), f.read(), 'image/png')

    email_message.send()


# Create your views here.
def watermark(request):
  if request.method == 'POST':
    image = request.FILES.get('image')
    secret_message = request.POST.get('secret_message')
    print(f"Received image: {image}, secret message: {secret_message}")
    # Save the image and secret message to the database
    img = Image(image=image, secret_message=secret_message)
    img.save()
    print(f"Image saved with ID: {img.id}")
    # Embed the secret message into the image
    watermarked_image = lsb.hide(img.image.path, secret_message)
    print(f"Watermarked image created: {watermarked_image}")
    # Save the watermarked image
    watermarked_path = os.path.join(settings.MEDIA_ROOT, 'watermarked_images', f'watermarked_{img.id}.png')
    watermarked_image.save(watermarked_path)

    send_email(
        email=request.POST.get('email'),
        subject='Your Watermarked Image',
        message='Here is your watermarked image with the secret message.',
        file_path=watermarked_path
    )

    print(f"Email sent with watermarked image: {watermarked_path} - {request.POST.get('email')}")

    return HttpResponse("Email sent successfully! Check your inbox.")  
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