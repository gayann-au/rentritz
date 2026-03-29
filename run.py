import os
import logging
from dotenv import load_dotenv

load_dotenv()

from waitress import serve
from app import create_app

app = create_app(os.environ.get('FLASK_ENV', 'production'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logging.info(f'RentRight Dubai starting on port {port}')
    serve(app, host='0.0.0.0', port=port, threads=8)