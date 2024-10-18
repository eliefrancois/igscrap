import instaloader
import os
import requests

# Initialize Instaloader with custom settings
L = instaloader.Instaloader(
    download_pictures=True,
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
def download_posts(profile_name):
    profile = instaloader.Profile.from_username(L.context, profile_name)
    
    for post in profile.get_posts():
        L.download_post(post, target=profile_name)

# Function to send file to Zapier webhook
def send_to_zapier(file_path, file_name):
    zapier_webhook_url = "https://hooks.zapier.com/hooks/catch/20456912/21er2s3/"
    
    with open(file_path, 'rb') as file:
        files = {'file': (file_name, file)}
        response = requests.post(zapier_webhook_url, files=files)
    
    if response.status_code == 200:
        print(f"Successfully sent {file_name} to Zapier")
    else:
        print(f"Failed to send {file_name} to Zapier. Status code: {response.status_code}")

# Main function
def main():
    profile_url = input("Enter the Instagram profile URL: ")
    profile_name = profile_url.split('/')[-2]  # Extract profile name from URL
    
    print(f"Downloading posts from {profile_name}...")
    download_posts(profile_name)
    
    print("Sending media files to Zapier...")
    for filename in os.listdir(profile_name):
        if filename.endswith(('.jpg', '.mp4')):
            file_path = os.path.join(profile_name, filename)
            send_to_zapier(file_path, filename)
    
    print("Process completed!")

if __name__ == "__main__":
    main()
