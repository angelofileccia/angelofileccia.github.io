#!/usr/bin/env python3
"""
Fetches reviews from GBP API (AZ + MI) and writes data/reviews.json.
Run via cron weekly. Saves to angelofileccia.github.io/data/reviews.json and commits.
"""

import json, urllib.request, urllib.parse, ssl, os, subprocess
from datetime import datetime, timezone

CREDS = os.path.expanduser('~/.openclaw/credentials')
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ctx = ssl.create_default_context()

ACCOUNT = 'accounts/117678848879456877615'
LOCATIONS = {
    'az': 'locations/17171931339559519986',
    'mi': 'locations/12078557571194838976',
}

def refresh_token():
    with open(f'{CREDS}/gbp.client') as f:
        lines = f.read().strip().splitlines()
        cid, csec = lines[0].strip(), lines[1].strip()
    rt = open(f'{CREDS}/gbp.refresh').read().strip()
    data = urllib.parse.urlencode({
        'client_id': cid, 'client_secret': csec,
        'refresh_token': rt, 'grant_type': 'refresh_token'
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    with urllib.request.urlopen(req, context=ctx) as r:
        tokens = json.loads(r.read())
    token = tokens['access_token']
    open(f'{CREDS}/gbp.token', 'w').write(token)
    os.chmod(f'{CREDS}/gbp.token', 0o600)
    return token

def fetch_reviews(token, location_id):
    url = f'https://mybusiness.googleapis.com/v4/{ACCOUNT}/{location_id}/reviews?pageSize=50'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            return json.loads(r.read()).get('reviews', [])
    except Exception as e:
        print(f'Warn: {e}')
        return []

star_map = {'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5}

token = refresh_token()
all_reviews = []
for loc_id in LOCATIONS.values():
    all_reviews += fetch_reviews(token, loc_id)

parsed = []
seen = set()
for r in sorted(all_reviews, key=lambda x: x.get('createTime', ''), reverse=True):
    stars = star_map.get(r.get('starRating', ''), 0)
    if not stars: continue
    comment = r.get('comment', '')
    key = (r['reviewer']['displayName'], comment[:40])
    if key in seen: continue
    seen.add(key)
    parsed.append({
        'name': r['reviewer']['displayName'],
        'stars': stars,
        'comment': comment,
        'date': r['createTime'][:10]
    })

total = len(parsed)
avg = round(sum(r['stars'] for r in parsed) / total, 1) if total else 0

output = {
    'averageRating': avg,
    'totalCount': total,
    'reviews': parsed[:8],
    'updatedAt': datetime.now(timezone.utc).strftime('%Y-%m-%d')
}

os.makedirs(f'{REPO}/data', exist_ok=True)
out_path = f'{REPO}/data/reviews.json'
with open(out_path, 'w') as f:
    json.dump(output, f, indent=2)

print(f'Saved {total} reviews (avg {avg}) to {out_path}')

# Git commit + push
subprocess.run(['git', '-C', REPO, 'add', 'data/reviews.json'], check=True)
result = subprocess.run(['git', '-C', REPO, 'diff', '--cached', '--quiet'])
if result.returncode != 0:
    pat = open(os.path.expanduser('~/.openclaw/credentials/github.token')).read().strip()
    subprocess.run(['git', '-C', REPO, 'commit', '-m', f'chore: refresh reviews ({output["updatedAt"]})'], check=True)
    remote = f'https://{pat}@github.com/angelofileccia/angelofileccia.github.io.git'
    subprocess.run(['git', '-C', REPO, 'push', remote, 'main'], check=True)
    print('Pushed to GitHub.')
else:
    print('No changes to commit.')
