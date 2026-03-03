from bs4 import BeautifulSoup
import requests

def get_title(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            title = soup.title.string if soup.title else 'No title found'
            return title
        else:
            return 'Error fetching URL'
    except requests.RequestException:
        return 'Error fetching URL'
