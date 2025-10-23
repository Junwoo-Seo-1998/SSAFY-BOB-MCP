import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from bob_server.server import get_meal_menu

# 테스트할 날짜
target_date = "2025-10-23"

print("--- 모든 층 메뉴---")
# 함수 호출 및 결과 출력 (모든 층)
formatted_menu_all = get_meal_menu(target_date)
print(formatted_menu_all)

print("\n--- 20F 메뉴---")
# 함수 호출 및 결과 출력 (20층만)
formatted_menu_20f = get_meal_menu(target_date, floor="20F")
print(formatted_menu_20f)