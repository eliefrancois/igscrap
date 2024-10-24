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

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

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

# Function to send file to Zapier webhook
"""
def send_to_zapier(file_path, file_name):
    zapier_webhook_url = "https://hooks.zapier.com/hooks/catch/20456912/21er2s3/"
    
    with open(file_path, 'rb') as file:
        files = {'file': (file_name, file)}
        response = requests.post(zapier_webhook_url, files=files)
    
    if response.status_code == 200:
        print(f"Successfully sent {file_name} to Zapier")
    else:
        print(f"Failed to send {file_name} to Zapier. Status code: {response.status_code}")
"""

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
def process_video(file_path):
    with VideoFileClip(file_path) as video:
        logging.info(f"Processing video: {file_path}")
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
        background = ColorClip(size=(target_width, target_height), color=(255, 255, 255), duration=video.duration)  # Create a blank white video
       
        # Overlay the cropped video on the white background
        final_video = CompositeVideoClip([background, video.set_position("center")])

        # Write the final video to the same file path, overwriting the original
        processed_video = final_video.write_videofile(file_path, codec='libx264', audio_codec='aac', remove_temp=True)  # Save the processed video
        logging.info(f"Processed video saved to: {file_path}")
        # return processed_video

@app.route('/process_instagram', methods=['POST'])
def process_instagram():
    profile_url = request.json.get('profile_url')
    if not profile_url:
        return jsonify({'error': 'No profile URL provided'}), 400

    profile_name = profile_url.split('/')[-2]  # Extract profile name from URL
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            download_dir = download_posts(profile_name, temp_dir)
            processed_files = []

            # Walk through the directory and its subdirectories
            for root, dirs, files in os.walk(download_dir):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    logging.info(f"Processing file: {file_path}")
                    if filename.endswith(('.jpg', '.jpeg')):
                        edit_image(file_path)
                        processed_files.append(file_path)
                    elif filename.endswith('.mp4'):
                        process_video(file_path)
                        processed_files.append(file_path)

            if not processed_files:
                logging.warning("No files were processed")
                return jsonify({'error': 'No files were processed'}), 404

            # Create a ZIP file containing all processed files
            memory_file = io.BytesIO()
            with zipfile.ZipFile(memory_file, 'w') as zf:
                for file_path in processed_files:
                    zf.write(file_path, os.path.relpath(file_path, download_dir))
            memory_file.seek(0)

            logging.info(f"Processed {len(processed_files)} files")
            return send_file(
                memory_file,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'{profile_name}_processed.zip'
            )
        except instaloader.exceptions.ProfileNotExistsException:
            logging.error(f"Profile {profile_name} does not exist")
            return jsonify({'error': f"Profile {profile_name} does not exist"}), 404
        except Exception as e:
            logging.error(f"Error processing Instagram profile: {str(e)}")
            return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)