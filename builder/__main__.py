"""시트 두 개를 다시 만든다: python -m builder

sheets/투자판단.xlsx       빈 양식(실제로 쓰는 파일)
sheets/투자판단_예시.xlsx  가상 데이터로 채운 예시
"""

from pathlib import Path

from .example import example_data
from .workbook import build

OUT = Path(__file__).resolve().parent.parent / "sheets"


def main():
    OUT.mkdir(exist_ok=True)
    build(OUT / "투자판단.xlsx")
    build(OUT / "투자판단_예시.xlsx", example_data())
    print(f"만듦: {OUT / '투자판단.xlsx'}, {OUT / '투자판단_예시.xlsx'}")


if __name__ == "__main__":
    main()
