# igscrap

igscrap is a command-line tool that downloads Instagram posts and sends them to a specified Zapier webhook. It's designed to simplify the process of collecting Instagram content for further processing or analysis.

## Features

- Download photos and videos from public Instagram profiles
- Automatically send downloaded media to a Zapier webhook
- Easy to use command-line interface

## Installation

You can install igscrap using pip:

```bash
pip install igscrap
```

## Usage

To use igscrap, run the following command:

```bash
igscrap <profile_url> <zapier_webhook_url>
```

Replace `<profile_url>` with the URL of the Instagram profile you want to download posts from.
Replace `<zapier_webhook_url>` with the URL of the Zapier webhook you want to send the posts to.

## Example

```bash
igscrap "https://www.instagram.com/natgeo/" "https://hooks.zapier.com/hooks/catch/1234567/abcdefg/"
```

This will download all the posts from the National Geographic Instagram profile and send them to the specified Zapier webhook.

## Requirements

- Python 3.6 or higher
- Internet connection
- Zapier account with a configured webhook

## Limitations

- This tool is designed for personal use and should be used responsibly.
- It may not work with private Instagram profiles.
- Instagram may rate-limit or block excessive requests.

## Contributing

Contributions to igscrap are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool is not affiliated with, authorized, maintained, sponsored or endorsed by Instagram or any of its affiliates or subsidiaries. This is an independent and unofficial tool. Use at your own risk.

## Support

If you encounter any problems or have any questions, please open an issue on the GitHub repository.

Remember to use this tool responsibly and in accordance with Instagram's terms of service.
