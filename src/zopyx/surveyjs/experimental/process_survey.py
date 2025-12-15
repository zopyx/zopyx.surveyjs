
import json
import smtplib
import weasyprint
import base64
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

def create_survey_email(json_path, sender, recipient):
    """
    Parses a SurveyJS JSON result file and generates a MIME message.

    Args:
        json_path (str): The path to the JSON result file.
        sender (str): The sender's email address.
        recipient (str): The recipient's email address.

    Returns:
        MIMEMultipart: The email message object.
    """
    with open(json_path, 'r') as f:
        results = json.load(f)

    msg = MIMEMultipart('related')
    msg['Subject'] = 'Survey Submission Results'
    msg['From'] = sender
    msg['To'] = recipient

    # Alternative part for HTML and plain text
    msg_alternative = MIMEMultipart('alternative')
    msg.attach(msg_alternative)

    html_body = "<h1>Survey Results</h1>"
    html_body += "<table border='1' cellpadding='5' cellspacing='0'>"
    html_body += "<tr><th>Question</th><th>Answer</th></tr>"

    for key, value in results.items():
        html_body += f"<tr><td><strong>{key}</strong></td><td>"
        if isinstance(value, list) and value:
            # Check if it looks like a file upload result
            item = value[0]
            if isinstance(item, dict) and 'name' in item and 'content' in item:
                if 'image' in item.get('type', ''):
                    image_data_uri = item['content']
                    html_body += f"""<div style='width:100%'><img src='{image_data_uri}' style='width:100%'></div>"""

                    # For email attachment
                    image_name = item['name']
                    header, data = item['content'].split(',')
                    image_data = base64.b64decode(data)
                    image = MIMEImage(image_data, name=image_name)
                    image.add_header('Content-Disposition', 'attachment', filename=image_name)
                    msg.attach(image)


                else:
                     html_body += f"Attached file: {item.get('name', 'N/A')}"
            else:
                html_body += "<br>".join(map(str, value))
        elif isinstance(value, dict):
            html_body += '<br>'.join([f'{k}: {v}' for k, v in value.items()])
        else:
            html_body += str(value)
        html_body += "</td></tr>"

    html_body += "</table>"
    
    # Attach the HTML body
    part = MIMEText(html_body, 'html')
    msg_alternative.attach(part)

    # Generate and attach PDF
    pdf_filename = "survey_results.pdf"
    weasyprint.HTML(string=html_body).write_pdf(pdf_filename)
    with open(pdf_filename, "rb") as f:
        pdf_attachment = MIMEApplication(f.read(), _subtype="pdf")
    pdf_attachment.add_header('Content-Disposition', 'attachment', filename=pdf_filename)
    msg.attach(pdf_attachment)

    return msg

def send_email(msg, smtp_server, smtp_port, smtp_user, smtp_password):
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
    msg = create_survey_email('result.json', 'info@zopyx.com', 'info@zopyx.com')
    mime_output = msg.as_string()
    print(mime_output)

    
    SMTP_CONFIG = {
        'smtp_server': 'smtp.mailbox.org',
        'smtp_port': 587,
        'smtp_user': 'zopyx@mailbox.org',
        'smtp_password': '01$$Yetsux'
    }
    try:
        send_email(msg, **SMTP_CONFIG)
        print("\nSuccessfully sent the email.")
    except Exception as e:
        print(f"\nFailed to send email: {e}")
