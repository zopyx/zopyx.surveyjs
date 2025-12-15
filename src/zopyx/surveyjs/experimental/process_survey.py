import json
import smtplib
import weasyprint
import base64
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def create_survey_email(json_path: str, sender: str, recipient: str) -> MIMEMultipart:
    """
    Parses a SurveyJS JSON result file and generates an email message (MIMEMultipart)
    with HTML content and image attachments.

    Args:
        json_path (str): The path to the JSON result file.

    Returns:
        MIMEMultipart: The email message object.
    """
    with open(json_path, "r") as f:
        results = json.load(f)

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = "Survey Results"  # Placeholder

    html_body = "<h1>Survey Results</h1>"
    html_body += "<table border='1' cellpadding='5' cellspacing='0'>"
    html_body += "<tr><th>Question</th><th>Answer</th></tr>"

    image_attachments = []

    for key, value in results.items():
        html_body += f"<tr><td><strong>{key}</strong></td><td>"
        if isinstance(value, list) and value:
            # Check if it looks like a file upload result
            item = value[0]
            if isinstance(item, dict) and "name" in item and "content" in item:
                if "image" in item.get("type", ""):
                    image_data_uri = item["content"]
                    html_body += f"""<div style='width:100%'><img src='{image_data_uri}' style='width:100%'></div>"""

                    # For email attachment
                    image_name = item["name"]
                    header, data = item["content"].split(",")
                    image_data = base64.b64decode(data)
                    image_subtype = item["type"].split("/")[-1]
                    image = MIMEImage(image_data, _subtype=image_subtype, name=image_name)
                    image.add_header(
                        "Content-Disposition", "attachment", filename=image_name
                    )
                    image_attachments.append(image)

                else:
                    html_body += f"Attached file: {item.get('name', 'N/A')}"
            else:
                html_body += "<br>".join(map(str, value))
        elif isinstance(value, str) and value.startswith("data:image/"):
            image_data_uri = value
            image_name = f"{key}.png"  # Use the key as filename, assume png for simplicity or try to parse from data URI

            html_body += f"""<div style='width:100%'><img src='{image_data_uri}' style='width:100%'></div>"""

            # For email attachment
            try:
                header, data = value.split(",", 1)
                image_type = header.split(":")[1].split(";")[0] # e.g. image/png
                image_data = base64.b64decode(data)
                # Attempt to get a more specific extension from the image_type
                extension = image_type.split('/')[-1]
                image_name = f"{key}.{extension}"
                image = MIMEImage(image_data, _subtype=extension, name=image_name)
                image.add_header(
                    "Content-Disposition", "attachment", filename=image_name
                )
                image_attachments.append(image)
            except Exception as e:
                print(f"Could not parse data URI for {key}: {e}")
                html_body += f"Error processing image for {key}"

        elif isinstance(value, dict):
            html_body += "<br>".join([f"{k}: {v}" for k, v in value.items()])
        else:
            html_body += str(value)
        html_body += "</td></tr>"

    html_body += "</table>"

    msg.attach(MIMEText(html_body, "html"))
    for img in image_attachments:
        msg.attach(img)

    return msg


def generate_pdf(html_content: str, pdf_filename: str) -> str:
    """
    Generates a PDF file from HTML content.

    Args:
        html_content (str): The HTML content to convert to PDF.
        pdf_filename (str): The name of the output PDF file.

    Returns:
        str: The filename of the generated PDF.
    """
    weasyprint.HTML(string=html_content).write_pdf(pdf_filename)
    return pdf_filename


def send_email(
    msg: MIMEMultipart,
    smtp_server: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
) -> None:
    """
    Sends the generated email to a configurable SMTP server.

    Args:
        msg: The MIMEMultipart message object to send.
        smtp_server (str): The SMTP server address.
        smtp_port (int): The SMTP server port.
        smtp_user (str): The username for SMTP authentication.
        smtp_password (str): The password for SMTP authentication.
    """
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)


if __name__ == "__main__":
    sender = "info@zopyx.com"
    recipient = "info@zopyx.com"
    msg = create_survey_email("result.json", sender, recipient)

    SMTP_CONFIG = {
        "smtp_server": "smtp.mailbox.org",
        "smtp_port": 587,
        "smtp_user": "zopyx@mailbox.org",
        "smtp_password": "01$$Yetsux",
    }
    try:
        send_email(msg, **SMTP_CONFIG)
        print("\nSuccessfully sent the email.")
    except Exception as e:
        print(f"\nFailed to send email: {e}")
