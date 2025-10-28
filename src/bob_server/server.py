import os
# UTF-8 인코딩을 강제 설정합니다. (Windows 환경 호환성)
os.environ['PYTHONIOENCODING'] = 'utf-8'
import sys
import json
from datetime import datetime, timedelta # timedelta 추가
from mcp.server.fastmcp import FastMCP, Context
from smithery.decorators import smithery
from pydantic import BaseModel, Field
from typing import Optional
import requests  # HTTP 요청을 위한 라이브러리
from dotenv import load_dotenv  # .env 파일 로드를 위해 추가

# --- 설정 및 환경 변수 로드 ---
#load_dotenv()  # .env 파일에서 환경 변수를 로드
#DATA_SOURCE_URL = os.environ.get("DATA_SOURCE_URL")
DATA_SOURCE_URL="https://soonga00.github.io/ssafy-meal-data/meals.json"

# --- 유틸리티 함수 (URL에서 직접 가져오도록 수정됨) ---
def fetch_data_from_url() -> dict:
    """외부 URL에서 실시간으로 JSON 데이터를 가져와 딕셔너리로 반환합니다."""
    
    # .env 파일에 URL이 설정되어 있는지 확인
    if not DATA_SOURCE_URL:
        sys.stderr.write("ERROR: DATA_SOURCE_URL environment variable is not set in .env file.\n")
        return {"error": "Server configuration error: DATA_SOURCE_URL not set."}

    try:
        # 1. URL에서 데이터 가져오기
        response = requests.get(DATA_SOURCE_URL)
        response.raise_for_status()  # HTTP 오류 (4xx, 5xx) 발생 시 예외 처리
        
        # 2. JSON 파싱
        data = response.json()
        sys.stderr.write(f"DEBUG: Data successfully fetched from {DATA_SOURCE_URL}\n")
        return data
        
    except requests.exceptions.RequestException as e:
        sys.stderr.write(f"ERROR: Failed to fetch data from URL: {e}\n")
        return {"error": f"Failed to fetch data from URL: {e}"}
    except json.JSONDecodeError:
        sys.stderr.write("ERROR: Failed to parse JSON response from URL.\n")
        return {"error": "Failed to parse JSON response."}

# --- 세션 설정 스키마 ---
class ConfigSchema(BaseModel):
    """SSAFY 식단 정보 서비스의 사용자 세션 설정을 정의합니다."""
    default_floor: Optional[str] = Field(None, description="자주 이용하는 식당 층을 설정합니다. (예: '10F', '20F')")

# --- 도구 인자 모델 (수정됨) ---
class GetMealMenuArgs(BaseModel):
    """get_meal_menu 도구의 인자를 정의합니다."""
    date: str = Field(..., description="메뉴를 조회할 날짜(YYYY-MM-DD 형식)입니다. 이 값은 필수입니다. 사용자의 질문에서 '오늘', '내일' 등 날짜 관련 언급이 있다면 그 날짜를, 별도 언급이 없다면 오늘 날짜를 YYYY-MM-DD 형식으로 변환하여 제공해야 합니다.")
    floor: Optional[str] = Field(None, description="메뉴를 조회할 층을 지정합니다. (예: \"10F\", \"20F\"). 지정하지 않으면 모든 층의 메뉴를 반환합니다.")


@smithery.server(config_schema=ConfigSchema)
def app():
    """Create and return a FastMCP server instance with session config."""
    mcp = FastMCP("SSAFYMealMenuService")

    # --- [수정된 부분] ---
    @mcp.tool(
        name="get_meal_menu",
        description="지정된 날짜(YYYY-MM-DD)의 SSAFY 식단 정보를 요일과 함께 포장하여 반환합니다."
    )
    def get_meal_menu(ctx: Context, args: GetMealMenuArgs) -> str:
        """지정된 날짜의 식단 메뉴를 가져옵니다. (도구 설명은 데코레이터로 이동)"""
        
        data = fetch_data_from_url() # 실시간 URL 호출로 변경
        
        if "error" in data:
            return data["error"]

        date_str = args.date

        # 이제 date_str은 LLM에 의해 항상 제공됩니다. (예: "2024-07-26")
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            day_of_week = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"][date_obj.weekday()]
        except ValueError:
            # LLM이 "오늘", "내일" 등을 YYYY-MM-DD로 변환하지 않고 그대로 보낸 경우
            return f"Error: LLM이 잘못된 날짜 형식으로 도구를 호출했습니다: '{args.date}'. YYYY-MM-DD 형식이 필요합니다."

        daily_data = data.get(date_str)
        if not daily_data:
            return f"Error: 해당 날짜({date_str})의 식단 데이터가 없습니다."
        
        # Pydantic 모델에서 floor 값을 가져옴
        target_floor = args.floor

        meals_by_floor = {}
        
        # daily_data가 리스트인지 확인 (JSON 구조에 따라)
        if not isinstance(daily_data, list):
             sys.stderr.write(f"ERROR: Expected list for date {date_str}, but got {type(daily_data)}.\n")
             return f"Error: 데이터 구조 오류. {date_str}의 데이터가 리스트 형태가 아닙니다."
        
        for meal in daily_data:
            meal_floor = meal.get("floor")
            
            # target_floor가 지정되었고, 현재 식단의 층과 다르면 건너뜀
            if target_floor and meal_floor and (target_floor.upper() != meal_floor.upper()):
                continue

            if meal_floor not in meals_by_floor:
                meals_by_floor[meal_floor] = []
            
            # 줄바꿈 문자를 쉼표+공백으로 변경하여 가독성 확보
            meal['name'] = meal.get('name', 'N/A').replace('\n', ', ')
            meals_by_floor[meal_floor].append(meal)

        if not meals_by_floor:
            return f"{date_str}에 {target_floor+'의 ' if target_floor else ''}메뉴 정보가 없습니다."

        floor_info = f"{target_floor} " if target_floor else ""
        formatted_output = f"📅 {date_str} ({day_of_week}) - 서울 캠퍼스 {floor_info}식단 메뉴 📋\n"
        formatted_output += "=" * 40 + "\n"

        for f, meals in sorted(meals_by_floor.items()):
            formatted_output += f"📍 {f}\n"
            for meal in meals:
                meal_type = meal.get('type', 'N/A')
                meal_name = meal.get('name', 'N/A') # 이미 위에서 \n 처리됨
                formatted_output += f"  - {meal_type}: {meal_name}\n"
            formatted_output += "-" * 20 + "\n"

        formatted_output += "=" * 40
        return formatted_output
        
    return mcp

