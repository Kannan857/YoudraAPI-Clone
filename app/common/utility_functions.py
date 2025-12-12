import re
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
import hashlib
import random
import string

async def generate_password(email: str, name: str, length: int = 12) -> str:
    # Combine email and name into one string
    base_str = email + name
    # Generate a SHA-256 hash of the combined string
    hash_digest = hashlib.sha256(base_str.encode()).hexdigest()
    # Take half the password length from the hash digest
    half_length = length // 2
    # Generate random characters (letters and digits) for the other half
    random_chars = ''.join(random.choices(string.ascii_letters + string.digits, k=length - half_length))
    # Combine both parts
    combined = list(hash_digest[:half_length] + random_chars)
    # Shuffle the characters to mix hash and random parts
    random.shuffle(combined)
    # Return the combined list as a string
    ret = f"Google- {''.join(combined)}"
    return ret


async def extract_number(text):
    """Finds numbers, ignoring spaces and non-numeric chars"""
    if not text:
        return 0
    numbers = re.findall(r'-?\d+\.?\d*', text)
    return float(numbers[0]) if numbers and '.' in numbers[0] else int(numbers[0]) if numbers else 0

async def send_email(name: str, email: str, token: str, template_id):
    message = Mail(
    from_email='kris@youdra.ai',
    to_emails= email,
    subject='Reset your password')
    message.dynamic_template_data = {
    'first_name': name,
    'token' : token,
    }
    message.template_id = 'd-80c86f6fb232412e993809229b084323'
    print (os.environ.get('SENDGRID_API_KEY'))
    print (f"len of the key is {len(os.environ.get('SENDGRID_API_KEY'))}")
    try:
        sendgrid_client = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        response = sendgrid_client.send(message)
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(e.message)

async def count_words_alpha_numeric(text):
    # Keep only sequences of alphabets or numbers as words
    words = re.findall(r'[a-zA-Z0-9]+', text)
    return len(words)