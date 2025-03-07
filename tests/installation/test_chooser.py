from __future__ import annotations

import re

from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

import pytest

from packaging.tags import Tag
from poetry.core.packages.package import Package

from poetry.installation.chooser import Chooser
from poetry.repositories.legacy_repository import LegacyRepository
from poetry.repositories.pool import Pool
from poetry.repositories.pypi_repository import PyPiRepository
from poetry.utils.env import MockEnv


if TYPE_CHECKING:
    import httpretty

    from httpretty.core import HTTPrettyRequest


JSON_FIXTURES = (
    Path(__file__).parent.parent / "repositories" / "fixtures" / "pypi.org" / "json"
)

LEGACY_FIXTURES = Path(__file__).parent.parent / "repositories" / "fixtures" / "legacy"


@pytest.fixture()
def env() -> MockEnv:
    return MockEnv(
        supported_tags=[
            Tag("cp37", "cp37", "macosx_10_15_x86_64"),
            Tag("py3", "none", "any"),
        ]
    )


@pytest.fixture()
def mock_pypi(http: type[httpretty.httpretty]) -> None:
    def callback(
        request: HTTPrettyRequest, uri: str, headers: dict[str, Any]
    ) -> list[int | dict[str, Any] | str] | None:
        parts = uri.rsplit("/")

        name = parts[-3]
        version = parts[-2]

        fixture = JSON_FIXTURES / name / (version + ".json")
        if not fixture.exists():
            fixture = JSON_FIXTURES / (name + ".json")

        if not fixture.exists():
            return

        with fixture.open(encoding="utf-8") as f:
            return [200, headers, f.read()]

    http.register_uri(
        http.GET,
        re.compile("^https://pypi.org/(.+?)/(.+?)/json$"),
        body=callback,
    )


@pytest.fixture()
def mock_legacy(http: type[httpretty.httpretty]) -> None:
    def callback(
        request: HTTPrettyRequest, uri: str, headers: dict[str, Any]
    ) -> list[int | dict[str, Any] | str]:
        parts = uri.rsplit("/")
        name = parts[-2]

        fixture = LEGACY_FIXTURES / (name + ".html")

        with fixture.open(encoding="utf-8") as f:
            return [200, headers, f.read()]

    http.register_uri(
        http.GET,
        re.compile("^https://foo.bar/simple/(.+?)$"),
        body=callback,
    )


@pytest.fixture()
def pool() -> Pool:
    pool = Pool()

    pool.add_repository(PyPiRepository(disable_cache=True))
    pool.add_repository(
        LegacyRepository("foo", "https://foo.bar/simple/", disable_cache=True)
    )

    return pool


@pytest.mark.parametrize("source_type", ["", "legacy"])
def test_chooser_chooses_universal_wheel_link_if_available(
    env: MockEnv, mock_pypi: None, mock_legacy: None, source_type: str, pool: Pool
):
    chooser = Chooser(pool, env)

    package = Package("pytest", "3.5.0")
    if source_type == "legacy":
        package = Package(
            package.name,
            package.version.text,
            source_type="legacy",
            source_reference="foo",
            source_url="https://foo.bar/simple/",
        )

    link = chooser.choose_for(package)

    assert link.filename == "pytest-3.5.0-py2.py3-none-any.whl"


@pytest.mark.parametrize(
    ("policy", "filename"),
    [
        (":all:", "pytest-3.5.0.tar.gz"),
        (":none:", "pytest-3.5.0-py2.py3-none-any.whl"),
        ("black", "pytest-3.5.0-py2.py3-none-any.whl"),
        ("pytest", "pytest-3.5.0.tar.gz"),
        ("pytest,black", "pytest-3.5.0.tar.gz"),
    ],
)
@pytest.mark.parametrize("source_type", ["", "legacy"])
def test_chooser_no_binary_policy(
    env: MockEnv,
    mock_pypi: None,
    mock_legacy: None,
    source_type: str,
    pool: Pool,
    policy: str,
    filename: str,
):
    chooser = Chooser(pool, env)
    chooser.set_no_binary_policy(policy)

    package = Package("pytest", "3.5.0")
    if source_type == "legacy":
        package = Package(
            package.name,
            package.version.text,
            source_type="legacy",
            source_reference="foo",
            source_url="https://foo.bar/simple/",
        )

    link = chooser.choose_for(package)

    assert link.filename == filename


@pytest.mark.parametrize("source_type", ["", "legacy"])
def test_chooser_chooses_specific_python_universal_wheel_link_if_available(
    env: MockEnv, mock_pypi: None, mock_legacy: None, source_type: str, pool: Pool
):
    chooser = Chooser(pool, env)

    package = Package("isort", "4.3.4")
    if source_type == "legacy":
        package = Package(
            package.name,
            package.version.text,
            source_type="legacy",
            source_reference="foo",
            source_url="https://foo.bar/simple/",
        )

    link = chooser.choose_for(package)

    assert link.filename == "isort-4.3.4-py3-none-any.whl"


@pytest.mark.parametrize("source_type", ["", "legacy"])
def test_chooser_chooses_system_specific_wheel_link_if_available(
    mock_pypi: None, mock_legacy: None, source_type: str, pool: Pool
):
    env = MockEnv(
        supported_tags=[Tag("cp37", "cp37m", "win32"), Tag("py3", "none", "any")]
    )
    chooser = Chooser(pool, env)

    package = Package("pyyaml", "3.13.0")
    if source_type == "legacy":
        package = Package(
            package.name,
            package.version.text,
            source_type="legacy",
            source_reference="foo",
            source_url="https://foo.bar/simple/",
        )

    link = chooser.choose_for(package)

    assert link.filename == "PyYAML-3.13-cp37-cp37m-win32.whl"


@pytest.mark.parametrize("source_type", ["", "legacy"])
def test_chooser_chooses_sdist_if_no_compatible_wheel_link_is_available(
    env: MockEnv,
    mock_pypi: None,
    mock_legacy: None,
    source_type: str,
    pool: Pool,
):
    chooser = Chooser(pool, env)

    package = Package("pyyaml", "3.13.0")
    if source_type == "legacy":
        package = Package(
            package.name,
            package.version.text,
            source_type="legacy",
            source_reference="foo",
            source_url="https://foo.bar/simple/",
        )

    link = chooser.choose_for(package)

    assert link.filename == "PyYAML-3.13.tar.gz"


@pytest.mark.parametrize("source_type", ["", "legacy"])
def test_chooser_chooses_distributions_that_match_the_package_hashes(
    env: MockEnv,
    mock_pypi: None,
    mock_legacy: None,
    source_type: str,
    pool: Pool,
):
    chooser = Chooser(pool, env)

    package = Package("isort", "4.3.4")
    files = [
        {
            "hash": "sha256:b9c40e9750f3d77e6e4d441d8b0266cf555e7cdabdcff33c4fd06366ca761ef8",  # noqa: E501
            "filename": "isort-4.3.4.tar.gz",
        }
    ]
    if source_type == "legacy":
        package = Package(
            package.name,
            package.version.text,
            source_type="legacy",
            source_reference="foo",
            source_url="https://foo.bar/simple/",
        )

    package.files = files

    link = chooser.choose_for(package)

    assert link.filename == "isort-4.3.4.tar.gz"


@pytest.mark.parametrize("source_type", ["", "legacy"])
def test_chooser_throws_an_error_if_package_hashes_do_not_match(
    env: MockEnv,
    mock_pypi: None,
    mock_legacy: None,
    source_type: None,
    pool: Pool,
):
    chooser = Chooser(pool, env)

    package = Package("isort", "4.3.4")
    files = [
        {
            "hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",  # noqa: E501
            "filename": "isort-4.3.4.tar.gz",
        }
    ]
    if source_type == "legacy":
        package = Package(
            package.name,
            package.version.text,
            source_type="legacy",
            source_reference="foo",
            source_url="https://foo.bar/simple/",
        )

    package.files = files

    with pytest.raises(RuntimeError) as e:
        chooser.choose_for(package)
    assert files[0]["hash"] in str(e)
