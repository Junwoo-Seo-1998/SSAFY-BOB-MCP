import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
import sys
import json
from datetime import datetime
from mcp.server.fastmcp import FastMCP, Context
from smithery.decorators import smithery
from pydantic import BaseModel, Field
from typing import Optional

# --- 설정 및 로컬 파일 경로 ---
DATA_FILE = "data/meals.json"

# --- 유틸리티 함수 ---
def load_local_data() -> dict:
    """로컬에 캐시된 JSON 파일을 로드하여 딕셔너리로 반환합니다."""
    try:
        if not os.path.exists(DATA_FILE):
            sys.stderr.write(f"ERROR: Data file not found at {DATA_FILE}. Did you run data_fetcher.py?\n")
            return {"error": "Local data file not found."}

        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        sys.stderr.write(f"ERROR: Failed to load or parse JSON data: {e}\n")
        return {"error": f"Failed to load JSON data: {e}"}

# --- 세션 설정 스키마 ---
class ConfigSchema(BaseModel):
    """SSAFY 식단 정보 서비스의 사용자 세션 설정을 정의합니다."""
    default_floor: Optional[str] = Field(None, description="자주 이용하는 식당 층을 설정합니다. (예: '10F', '20F')")

# --- 도구 인자 모델 ---
class GetMealMenuArgs(BaseModel):
    """get_meal_menu 도구의 인자를 정의합니다."""
    date: str = Field(..., description="YYYY-MM-DD 형식의 날짜입니다. LLM이 사용자의 자연어(예: '오늘')를 이 형식으로 변환하여 전달합니다.")
    floor: Optional[str] = Field(None, description="메뉴를 조회할 층을 지정합니다. (예: \"10F\", \"20F\"). 지정하지 않으면 모든 층의 메뉴를 반환합니다.")

@smithery.server(config_schema=ConfigSchema)
def app():
    """Create and return a FastMCP server instance with session config."""
    mcp = FastMCP("SSAFYMealMenuService")

    @mcp.resource("ssafy:cached_meal_data")
    def get_local_cached_meal_data() -> str:
        """로컬에 캐시된 JSON 파일의 전체 내용을 LLM에게 컨텍스트로 제공합니다."""
        data = load_local_data()
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool()
    def get_meal_menu(ctx: Context, args: GetMealMenuArgs) -> str:
        """
        지정된 날짜의 식단 메뉴를 가져옵니다.
        """
        data = load_local_data()
        
        if "error" in data:
            return data["error"]

        try:
            date_obj = datetime.strptime(args.date, "%Y-%m-%d")
            day_of_week = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"][date_obj.weekday()]
        except ValueError:
            return f"Error: LLM이 잘못된 날짜 형식으로 도구를 호출했습니다: '{args.date}'. YYYY-MM-DD 형식이 필요합니다."

        date_str = args.date
        daily_data = data.get(date_str)
        if not daily_data:
            return f"Error: 해당 날짜({date_str})의 식단 데이터가 없습니다."

        target_floor = args.floor

        meals_by_floor = {}
        for meal in daily_data:
            meal_floor = meal.get("floor")
            
            if target_floor and target_floor.upper() != meal_floor.upper():
                continue

            if meal_floor not in meals_by_floor:
                meals_by_floor[meal_floor] = []
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
                meal_name = meal.get('name', 'N/A').replace(',', ', ')
                formatted_output += f"  - {meal_type}: {meal_name}\n"
            formatted_output += "-" * 20 + "\n"

        formatted_output += "=" * 40
        return formatted_output
        
    return mcp