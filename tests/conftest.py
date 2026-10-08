import os
import shutil
import subprocess
from pathlib import Path

import openpyxl
import pytest

from builder.example import example_data
from builder.workbook import build

from .edge_data import edge_data


def recalc(path: Path, outdir: Path) -> Path:
    """LibreOffice로 수식을 계산해 값이 들어간 사본을 만든다."""
    profile = outdir / "lo-profile"
    subprocess.run(
        [
            shutil.which("soffice"),
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(outdir / "calc"),
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=900,
        env={**os.environ, "SAL_USE_VCLPLUGIN": "svp"},
    )
    return outdir / "calc" / path.name


needs_soffice = pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice(soffice)가 없음")


CASES = {"example": example_data, "edge": edge_data}


@pytest.fixture(scope="session", params=sorted(CASES))
def case(request, tmp_path_factory):
    """(입력 데이터, LibreOffice로 계산한 시트). 예시 데이터와 덜 채운 데이터 두 가지."""
    data = CASES[request.param]()
    d = tmp_path_factory.mktemp(request.param)
    src = d / f"{request.param}.xlsx"
    build(src, data)
    return data, openpyxl.load_workbook(recalc(src, d), data_only=True)


@pytest.fixture(scope="session")
def template_book(tmp_path_factory):
    d = tmp_path_factory.mktemp("template")
    src = d / "template.xlsx"
    build(src)
    return openpyxl.load_workbook(recalc(src, d), data_only=True)
