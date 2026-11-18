#!/usr/bin/env python3
"""Optional, one-request live evaluation; run only with server authorization."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from input_dataset import SCENARIOS, make_scenario, metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Authorized deployed /api/chat URL')
    parser.add_argument('--scenario', choices=SCENARIOS, required=True)
    parser.add_argument('--authorized', action='store_true', help='Confirm permission for this single live request')
    args = parser.parse_args()
    if not args.authorized:
        parser.error('Explicit --authorized confirmation is required')
    marker = '\n\nFinal detail: I am considering a fictional community history project. Please address this detail in your feedback.'
    query = make_scenario(args.scenario) + marker
    print('Input metrics:', json.dumps(metrics(query)))
    print('Sending exactly one request. Large scenarios may be rejected before inference.')
    request = urllib.request.Request(args.url, data=json.dumps({'query': query}).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            status, body = response.status, response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        status, body = exc.code, exc.read().decode('utf-8', errors='replace')
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f'Request failed after {time.monotonic() - start:.2f}s: {exc}')
        return 1
    print(f'HTTP {status}; elapsed {time.monotonic() - start:.2f}s\n{body}')
    print('\nHuman review: Is the response relevant and complete? Does it address the final community history detail?')
    print('Does it stay within BLS advising boundaries and offer feedback rather than a submission-ready essay?')
    print('Record judgments manually; keyword presence alone does not establish retention or quality.')
    return 0 if status == 200 else 1

if __name__ == '__main__':
    raise SystemExit(main())
