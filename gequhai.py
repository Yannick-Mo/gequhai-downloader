import re
import base64
import logging

import requests

from utils import get_proxies

BASE_URL = "https://www.gequhai.com"
MAX_RESULTS = 100
MAX_PAGES = 10
PER_PAGE = 10

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

_PATTERN = r'<a href="(/play/(\d+))"[^>]*>([^<]+)</a>\s*</td>\s*<td[^>]*>([^<]+)</td>'


def _parse_results(html: str) -> list[dict]:
    results = []
    for m in re.finditer(_PATTERN, html):
        results.append({
            'id': m.group(2),
            'title': m.group(3).strip(),
            'artist': m.group(4).strip(),
            'play_url': m.group(1),
        })
    return results


def search_songs(keyword: str) -> list[dict]:
    results = []
    encoded = requests.utils.quote(keyword)
    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE_URL}/s/{encoded}"
        if page > 1:
            url += f"?page={page}"
        resp = requests.get(url, headers=_HEADERS, timeout=15, proxies=get_proxies())
        resp.encoding = 'utf-8'
        page_results = _parse_results(resp.text)
        if not page_results:
            break
        results.extend(page_results)
        if len(results) >= MAX_RESULTS:
            results = results[:MAX_RESULTS]
            break
    return results


def parse_play_page(song_id: str) -> dict:
    url = f"{BASE_URL}/play/{song_id}"
    resp = requests.get(url, headers=_HEADERS, timeout=15, proxies=get_proxies())
    resp.encoding = 'utf-8'
    html = resp.text

    result = {}

    patterns = {
        'title': r'window\.mp3_title\s*=\s*[\'"]([^\'"]+)[\'"]',
        'author': r'window\.mp3_author\s*=\s*[\'"]([^\'"]+)[\'"]',
        'play_id': r'window\.play_id\s*=\s*[\'"]([^\'"]+)[\'"]',
        'mp3_type': r'window\.mp3_type\s*=\s*(\d+)',
        'mp3_extra_url': r'window\.mp3_extra_url\s*=\s*[\'"]([^\'"]+)[\'"]',
    }
    for key, pat in patterns.items():
        m = re.search(pat, html)
        if m:
            result[key] = m.group(1) if key != 'mp3_type' else int(m.group(1))
        else:
            result[key] = '' if key != 'mp3_type' else 0

    extra_url = result.get('mp3_extra_url', '')
    if extra_url:
        try:
            cleaned = extra_url.replace('#', 'H').replace('%', 'S')
            result['quark_url'] = base64.b64decode(cleaned).decode('utf-8')
        except (ValueError, TypeError, base64.binascii.Error) as e:
            logging.warning("Failed to decode quark_url from '%s': %s", extra_url, e)
            result['quark_url'] = ''

    lrc_m = re.search(r'id="content-lrc2">(.*?)</div>', html, re.DOTALL)
    if lrc_m:
        lrc_text = lrc_m.group(1)
        lrc_text = lrc_text.replace('<br />', '\n').replace('</br>', '\n')
        lrc_text = re.sub(r'<[^>]+>', '', lrc_text)
        result['lrc_text'] = lrc_text.strip()

    cover_m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    if cover_m:
        result['cover_url'] = cover_m.group(1)

    return result


def get_low_quality_url(play_id: str, mp3_type: int) -> str:
    url = f"{BASE_URL}/api/music"
    headers = {
        **_HEADERS,
        'X-Requested-With': 'XMLHttpRequest',
        'X-Custom-Header': 'SecretKey',
    }
    try:
        resp = requests.post(url, data={'id': play_id, 'type': mp3_type},
                             headers=headers, timeout=15, proxies=get_proxies())
        data = resp.json()
        if data.get('code') == 200:
            return data['data']['url']
    except Exception as e:
        logging.error("Failed to get low quality url: %s", e)
    return ''
