import pytest

from mime import __version__
from mime.cli import main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(['--version'])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f'mime {__version__}'


def test_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert 'usage: mime' in capsys.readouterr().out
