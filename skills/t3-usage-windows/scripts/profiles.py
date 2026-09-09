"""Provider matching uses exact IDs first, otherwise ID/display-name substrings."""
import json
import os
from pathlib import Path


def settings():
    path = Path(os.environ.get('T3CODE_HOME', Path.home() / '.t3')) / 'userdata/settings.json'
    return json.loads(path.read_text())


def matching(query, ids):
    names = settings().get('providerInstances', {})
    selected = set()
    for part in query.split(','):
        low = part.strip().casefold()
        if not low:
            continue
        exact = {i for i in ids if i.casefold() == low}
        selected.update(exact or {i for i in ids if low in i.casefold() or low in (names.get(i, {}).get('displayName') or '').casefold()})
    return selected


def filter_rows(rows, query):
    wanted = matching(query, {row['instance_id'] for row in rows})
    return [row for row in rows if row['instance_id'] in wanted]
