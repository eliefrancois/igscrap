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
from celery import Celery
from celery_config import make_celery
from pathlib import Path
import time

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('instagram_scraper.log')
    ]
)

app = Flask(__name__)
CORS(app)
celery = Celery('igscrape',
                broker='redis://localhost:6379/0',
                backend='redis://localhost:6379/0')

# Add basic rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["1000 per minute"]
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

# Create a constant for the download directory
DOWNLOAD_DIR = Path(os.path.expanduser('~/Desktop')) / 'instagram_downloads'
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Define the task
@celery.task(bind=True)
def process_instagram_task(self, profile_url):
    try:
        # Extract profile name from URL
        profile_name = profile_url.rstrip('/').split('/')[-1]
        logging.info(f"Processing profile: {profile_name}")
        
        # Create a unique directory for this task
        task_dir = DOWNLOAD_DIR / self.request.id
        logging.info(f"Created task directory at: {task_dir}")
        task_dir.mkdir(exist_ok=True)
        
        # Set the zip path
        zip_path = task_dir / f"{profile_name}_processed.zip"
        logging.info(f"ZIP will be created at: {zip_path}")
        
        # Initial state
        self.update_state(state='DOWNLOADING', meta={'progress': 0})
        logging.info("Starting download phase...")
        
        # Download posts
        self.update_state(state='DOWNLOADING', meta={'progress': 25})
        download_dir = download_posts(profile_name, task_dir)
        logging.info(f"Downloads completed. Files in: {download_dir}")
        
        processed_files = []

        # Process files
        self.update_state(state='PROCESSING', meta={'progress': 50})
        logging.info("Starting file processing...")
        
        for root, dirs, files in os.walk(download_dir):
            logging.info(f"Scanning directory: {root}")
            logging.info(f"Found files: {files}")
            
            for filename in files:
                file_path = os.path.join(root, filename)
                logging.info(f"Processing file: {file_path}")
                
                if filename.endswith('.mp4'):
                    logging.info(f"Processing video: {filename}")
                    process_video(file_path, bypass_editing=True)
                    processed_files.append(file_path)
                    logging.info(f"Video processed successfully: {filename}")

        if not processed_files:
            logging.warning("No files were processed!")
            return {'status': 'error', 'message': 'No files were processed'}

        # Finalizing
        self.update_state(state='FINALIZING', meta={'progress': 75})
        logging.info("Starting finalization phase...")

        # Create the ZIP file
        logging.info(f"Creating ZIP file at: {zip_path}")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for video in processed_files:
                logging.info(f"Adding to ZIP: {video}")
                zipf.write(video, os.path.basename(video))
                logging.info(f"Removing processed file: {video}")
                os.remove(video)

        logging.info(f"ZIP file created successfully at: {zip_path}")
        logging.info(f"ZIP file exists: {zip_path.exists()}")
        logging.info(f"ZIP file size: {zip_path.stat().st_size} bytes")
        
        return {
            'status': 'success',
            'zip_path': str(zip_path),
            'profile_name': profile_name
        }

    except Exception as e:
        logging.error(f"Error processing Instagram profile: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'message': str(e)
        }

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
def download_posts(profile_name, task_dir):
    logging.info(f"Starting download for profile: {profile_name} to directory: {task_dir}")
    profile = instaloader.Profile.from_username(L.context, profile_name)
    posts = islice(profile.get_posts(), 10)
    
    # Create a subdirectory for the profile inside the task directory
    target_dir = os.path.join(task_dir, profile_name)
    logging.info(f"Creating target directory at: {target_dir}")
    os.makedirs(target_dir, exist_ok=True)
    
    # Change the working directory to the target directory
    original_dir = os.getcwd()
    logging.info(f"Current directory: {original_dir}")
    os.chdir(target_dir)
    logging.info(f"Changed to directory: {target_dir}")
    
    try:
        for post in posts:
            logging.info(f"Downloading post: {post.shortcode}")
            L.download_post(post, target=profile_name)
    finally:
        # Change back to the original directory
        os.chdir(original_dir)
        logging.info(f"Changed back to directory: {original_dir}")
    
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
@limiter.limit("1000 per minute")  # Specific rate limit for this endpoint
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
    try:
        logging.info(f"Checking status for task: {task_id}")
        task = process_instagram_task.AsyncResult(task_id)
        
        if not task.ready():
            progress = task.info.get('progress', 0) if task.info else 0
            logging.info(f"Task {task_id} still processing. Progress: {progress}%")
            return jsonify({
                'status': 'processing',
                'progress': progress
            })
        
        result = task.get()
        logging.info(f"Task result: {result}")
        
        if result['status'] == 'success':
            zip_path = Path(result['zip_path'])
            logging.info(f"Looking for ZIP file at: {zip_path}")
            logging.info(f"ZIP file exists: {zip_path.exists()}")
            
            if not zip_path.exists():
                logging.error(f"ZIP file not found at: {zip_path}")
                return jsonify({
                    'status': 'error',
                    'message': 'ZIP file not found'
                }), 404
            
            try:
                logging.info(f"Sending file: {zip_path}")
                return send_file(
                    zip_path,
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name=f"{result['profile_name']}_processed.zip"
                )
            except Exception as e:
                logging.error(f"Error sending file: {str(e)}", exc_info=True)
                return jsonify({
                    'status': 'error',
                    'message': f'Error sending file: {str(e)}'
                }), 500
        else:
            logging.error(f"Task failed: {result.get('message', 'Unknown error')}")
            return jsonify({
                'status': 'error',
                'message': result.get('message', 'Unknown error')
            }), 500
            
    except Exception as e:
        logging.error(f"Error checking task status: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@celery.task
def cleanup_old_files():
    try:
        # Delete files older than 1 hour
        cutoff = time.time() - 3600
        
        for task_dir in DOWNLOAD_DIR.iterdir():
            if task_dir.is_dir():
                # Check if directory is empty
                if not any(task_dir.iterdir()):
                    task_dir.rmdir()
                    continue
                
                # Check files in directory
                for file_path in task_dir.iterdir():
                    if file_path.stat().st_mtime < cutoff:
                        file_path.unlink()
                
                # Try to remove directory if empty
                if not any(task_dir.iterdir()):
                    task_dir.rmdir()
                    
    except Exception as e:
        logging.error(f"Error cleaning up files: {str(e)}")

# Schedule cleanup task
@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        300.0,  # Run every 5 minutes
        cleanup_old_files.s(),
        name='cleanup-old-files'
    )

@app.route('/cleanup', methods=['POST'])
def trigger_cleanup():
    try:
        cleanup_old_files.delay()
        return jsonify({
            'status': 'success',
            'message': 'Cleanup task started'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    # Get port from environment variable or default to 5001
    port = int(os.environ.get('PORT', 5001))
    
    logging.info(f"Starting Flask server on port {port}")
    app.run(debug=True, host='0.0.0.0', port=port)
