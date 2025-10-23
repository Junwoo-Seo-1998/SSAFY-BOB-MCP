# data_fetcher.py

import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv # .env 파일 로드용


load_dotenv()
# 외부 데이터 소스 URL
DATA_URL = os.getenv("DATA_SOURCE_URL")
# 로컬 저장 경로
OUTPUT_DIR = os.getenv("DATA_CACHE_DIR", "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, os.getenv("DATA_CACHE_FILENAME", "meals.json"))

def fetch_and_save_data():
    """
    외부 URL에서 JSON 데이터를 가져와 로컬 파일에 저장합니다.
    """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Attempting to fetch data from: {DATA_URL}")

    try:
        # 1. 외부 JSON 데이터 가져오기
        response = requests.get(DATA_URL, timeout=10)
        response.raise_for_status() # HTTP 오류가 발생하면 예외 발생

        # 2. JSON 파싱
        remote_data = response.json()

        # 3. 출력 디렉토리가 없으면 생성
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # 4. 로컬 파일에 저장 (인코딩 및 들여쓰기 설정)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            # 원본 데이터 구조를 그대로 저장하여 MCP 서버가 사용하도록 함
            json.dump(remote_data, f, ensure_ascii=False, indent=2)
        
        print(f"Success! Data saved to {OUTPUT_FILE}")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    except json.JSONDecodeError:
        print("Error: Could not decode response as JSON.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    fetch_and_save_data()
