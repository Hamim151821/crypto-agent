import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('CRYPTOPANIC_TOKEN')
url = 'https://cryptopanic.com/api/v1/posts/'
params = {'auth_token': token, 'currencies': 'BTC', 'public': 'true'}
r = requests.get(url, params=params)
print(r.status_code)
print(r.json())