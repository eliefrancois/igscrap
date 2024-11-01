from igscrape import celery, process_instagram_task

# This ensures the task is registered properly
if __name__ == '__main__':
    celery.start() 