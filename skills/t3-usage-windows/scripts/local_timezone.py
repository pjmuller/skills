"""System timezone with daylight-saving rules, including future scheduled dates."""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def system_timezone():
    if os.environ.get('TZ'):
        return ZoneInfo(os.environ['TZ'].removeprefix(':'))
    try:
        with Path('/etc/localtime').open('rb') as stream:
            return ZoneInfo.from_file(stream)
    except OSError:
        return datetime.now().astimezone().tzinfo
