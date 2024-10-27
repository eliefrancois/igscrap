from itertools import islice
from flask import Flask, request, jsonify, send_file
import instaloader
import os
import requests
from PIL import Image
from moviepy.editor import VideoFileClip, CompositeVideoClip
import moviepy.video.fx as vfx
from moviepy.video.VideoClip import ColorClip
import tempfile
import shutil
import zipfile
import io
import logging
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from celery_config import make_celery

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('instagram_scraper.log')
    ]
)

app = Flask(__name__)
CORS(app)
celery = make_celery(app)

# Add basic rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day", "10 per hour"]
)
webhook_url = "https://discord.com/api/webhooks/1299118207864537141/SZ3aoV2FzUmTkI-tBsQ5YKGHKjlfPorr11LPNc4pa-t2oqAwonY0vtOitTWrrU8603z-"

def send_discord_notification(webhook_url, profile_url, num_videos):
    message = f"Videos have been processed successfully!\nProfile URL: {profile_url}\nNumber of videos: {num_videos}"
    data = {
        "content": message
    }
    response = requests.post(webhook_url, json=data)
    
    if response.status_code == 204:
        logging.info("Notification sent successfully.")
    else:
        logging.error(f"Failed to send notification. Status code: {response.status_code}, Response: {response.text}")

# Define the task
@celery.task(bind=True)
def process_instagram_task(self, profile_url):
    try:
        # Initial state
        self.update_state(state='DOWNLOADING', meta={'progress': 0})
        profile_name = profile_url.split('/')[-2]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Download posts
            self.update_state(state='DOWNLOADING', meta={'progress': 25})
            download_dir = download_posts(profile_name, temp_dir)
            processed_files = []

            # Process files
            self.update_state(state='PROCESSING', meta={'progress': 50})
            for root, dirs, files in os.walk(download_dir):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    logging.info(f"Processing file: {file_path}")
                    if filename.endswith('.mp4'):
                        process_video(file_path, bypass_editing=True)
                        processed_files.append(file_path)

            if not processed_files:
                return {'status': 'error', 'message': 'No files were processed'}

            # Finalizing
            self.update_state(state='FINALIZING', meta={'progress': 75})

            # Send Discord notification
            num_videos = len([f for f in processed_files if f.endswith('.mp4')])
            send_discord_notification(webhook_url, profile_url, num_videos)

            # Create ZIP file
            memory_file = io.BytesIO()
            with zipfile.ZipFile(memory_file, 'w') as zf:
                for file_path in processed_files:
                    zf.write(file_path, os.path.relpath(file_path, download_dir))
            
            # Finalizing
            self.update_state(state='FINALIZING', meta={'progress': 100})
            temp_zip_path = os.path.join(temp_dir, f'{profile_name}_processed.zip')
            with open(temp_zip_path, 'wb') as f:
                f.write(memory_file.getvalue())

            return {
                'status': 'success',
                'zip_path': temp_zip_path,
                'profile_name': profile_name
            }

    except Exception as e:
        logging.error(f"Error processing Instagram profile: {str(e)}")
        return {'status': 'error', 'message': str(e)}

# Add a health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

# Initialize Instaloader with custom settings
L = instaloader.Instaloader(
    download_pictures=False,
    download_videos=True,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False,
    post_metadata_txt_pattern="",
    storyitem_metadata_txt_pattern=None,
)

# Function to download posts from a profile
def download_posts(profile_name, temp_dir):
    profile = instaloader.Profile.from_username(L.context, profile_name)
    posts = islice(profile.get_posts(), 10)
    
    # Create a subdirectory for the profile
    target_dir = os.path.join(temp_dir, profile_name)
    os.makedirs(target_dir, exist_ok=True)
    
    # Change the working directory to the target directory
    original_dir = os.getcwd()
    os.chdir(target_dir)
    
    try:
        for post in posts:
            L.download_post(post, target=profile_name)
    finally:
        # Change back to the original directory
        os.chdir(original_dir)
    
    logging.info(f"Posts downloaded to: {target_dir}")
    return target_dir

# Function to edit images to 9:16 aspect ratio with a white background (if not already)
def edit_image(file_path):
    with Image.open(file_path) as img:
        # Calculate current aspect ratio
        width, height = img.size
        current_ratio = width / height
        
        # Check if the image is already in 9:16 aspect ratio
        if current_ratio == (9 / 16):
            print(f"Skipping {file_path}: already in 9:16 aspect ratio.")
            return  # Skip processing if the aspect ratio is already correct

        # Calculate new dimensions
        new_height = int(width * 16 / 9)
        
        # Create a new white background image
        new_img = Image.new("RGB", (width, new_height), (255, 255, 255))
        
        # Calculate position to paste the original image
        paste_y = (new_height - height) // 2
        new_img.paste(img, (0, paste_y))
        
        # Save the edited image
        new_img.save(file_path)

# Function to process videos to 9:16 aspect ratio with a white background (if not already)
def process_video(file_path, bypass_editing=False):
    with VideoFileClip(file_path) as video:
        logging.info(f"Processing video: {file_path}")
        
        if bypass_editing:
            logging.info(f"Bypassing video editing for: {file_path}")
            return  # Skip processing and return immediately

        # Calculate current aspect ratio
        current_ratio = video.w / video.h
        
        # Check if the video is already in 9:16 aspect ratio
        if current_ratio == (9 / 16):
            print(f"Skipping {file_path}: already in 9:16 aspect ratio.")
            return  # Skip processing if the aspect ratio is already correct

        # Calculate target dimensions for 9:16 aspect ratio
        target_width = 1080  # You can adjust this as needed
        target_height = int(target_width * 16 / 9)

        if current_ratio > (9 / 16):
            # Video is too wide, crop width
            new_width = int(video.h * (9 / 16))
            new_height = video.h
            video = video.crop(x_center=video.w / 2, y_center=video.h / 2, width=new_width, height=new_height)
        else:
            # Video is too tall, crop height
            new_width = video.w
            new_height = int(video.w * (16 / 9))
            video = video.crop(x_center=video.w / 2, y_center=video.h / 2, width=new_width, height=new_height)

        # Create a new video clip with a white background
        background = ColorClip(size=(target_width, target_height), color=(255, 255, 255), duration=video.duration)
       
        # Overlay the cropped video on the white background
        final_video = CompositeVideoClip([background, video.set_position("center")])

        # Write the final video to the same file path, overwriting the original
        processed_video = final_video.write_videofile(file_path, codec='libx264', audio_codec='aac', remove_temp=True)
        logging.info(f"Processed video saved to: {file_path}")

@app.route('/process_instagram', methods=['POST'])
@limiter.limit("10 per hour")  # Specific rate limit for this endpoint
def process_instagram():
    profile_url = request.json.get('profile_url')
    if not profile_url:
        return jsonify({'error': 'No profile URL provided'}), 400

    # Start the Celery task
    task = process_instagram_task.delay(profile_url)
    
    # Return the task ID to the client
    return jsonify({
        'task_id': task.id,
        'status': 'Processing started'
    })

# Add a route to check task status
@app.route('/task_status/<task_id>', methods=['GET'])
def task_status(task_id):
    task = process_instagram_task.AsyncResult(task_id)
    if task.ready():
        result = task.get()
        if result['status'] == 'success':
            # Return the processed ZIP file
            return send_file(
                result['zip_path'],
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"{result['profile_name']}_processed.zip"
            )
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 400
    return jsonify({'status': 'processing'})

if __name__ == '__main__':
    # Get port from environment variable or default to 5001
    port = int(os.environ.get('PORT', 5001))
    
    logging.info(f"Starting Flask server on port {port}")
    app.run(debug=True, host='0.0.0.0', port=port)
