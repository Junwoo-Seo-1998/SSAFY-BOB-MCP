import os
# UTF-8 인코딩을 강제 설정합니다. (Windows 환경 호환성)
os.environ['PYTHONIOENCODING'] = 'utf-8'
import sys
import json
from datetime import datetime, timedelta # timedelta 추가
from mcp.server.fastmcp import FastMCP, Context
from smithery.decorators import smithery
from pydantic import BaseModel, Field, field_validator # field_validator 추가
from typing import Optional
import requests  # HTTP 요청을 위한 라이브러리
from dotenv import load_dotenv  # .env 파일 로드를 위해 추가

# --- 설정 및 환경 변수 로드 ---
load_dotenv()  # .env 파일에서 환경 변수를 로드
DATA_SOURCE_URL = os.environ.get("DATA_SOURCE_URL")

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
    # [수정] 빈 값일 때 "오늘"이 아닌, 데이터상 "최신 날짜"를 사용하도록 유도
    date: str = Field(..., description="YYYY-MM-DD 형식의 날짜입니다. LLM이 사용자의 자연어(예: '오늘', '내일')를 이 형식으로 변환하여 전달합니다. 빈 값으로 전달되면 데이터 소스에 있는 최신 날짜로 자동 설정됩니다.")
    floor: Optional[str] = Field(None, description="메뉴를 조회할 층을 지정합니다. (예: \"10F\", \"20F\"). 지정하지 않으면 모든 층의 메뉴를 반환합니다.")

    @field_validator('date', mode='before')
    @classmethod
    def handle_date_input(cls, v: any) -> str:
        """
        LLM이 빈 값(None, "")을 전달하면, "최신 날짜 사용" 마커를 반환합니다.
        """
        value_str = str(v).strip().lower() if v is not None else ""
        
        if value_str == "":
            # [수정] 빈 값이면 "오늘 날짜" 대신 "최신 날짜 사용" 마커 반환
            sys.stderr.write(f"DEBUG: Empty date input received. Defaulting to LATEST available date.\n")
            return "USE_LATEST_DATE"
        
        # YYYY-MM-DD 형식이나 "오늘", "내일" 등 (LLM이 잘못 보낸 값)은 그대로 통과
        return str(v)


@smithery.server(config_schema=ConfigSchema)
def app():
    """Create and return a FastMCP server instance with session config."""
    mcp = FastMCP("SSAFYMealMenuService")

    @mcp.resource("ssafy:live_meal_data") # 로컬 캐시가 아닌 실시간 데이터를 반영하도록 이름 변경
    def get_live_meal_data() -> str:
        """(실시간) URL에서 JSON 파일의 전체 내용을 LLM에게 컨텍스트로 제공합니다."""
        data = fetch_data_from_url() # 실시간 URL 호출로 변경
        return json.dumps(data, ensure_ascii=False, indent=2)

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

        # [수정] Validator가 "USE_LATEST_DATE"를 반환했는지 확인
        if date_str == "USE_LATEST_DATE":
            if not data: # 데이터가 비어있는지 확인
                return "Error: 데이터 소스에서 식단 정보를 찾을 수 없습니다."
            
            # JSON 데이터의 첫 번째 날짜 키(데이터상 최신 날짜)를 사용
            date_str = next(iter(data.keys()), None)
            
            if date_str is None:
                 return "Error: 데이터 소스에 유효한 날짜가 없습니다."
            sys.stderr.write(f"DEBUG: Using latest available date from data source: {date_str}\n")

        # 이제 date_str은 "2024-07-26" (데이터상 최신 날짜) 또는 "2024-07-24" (사용자 지정)
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

