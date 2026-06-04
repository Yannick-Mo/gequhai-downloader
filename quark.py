import json
import logging
import os
import time
from urllib.parse import urlparse

import requests

from utils import download_file, safe_filename, get_proxies

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

_JSON_HEADERS = {
    **_HEADERS,
    'Origin': 'https://pan.quark.cn',
    'Referer': 'https://pan.quark.cn/',
    'Content-Type': 'application/json',
}

AUDIO_EXTS = ('.mp3', '.ogg', '.aac')
MAX_RECURSION = 50
TASK_POLL_MAX = 30


def _api_data(resp: requests.Response) -> dict | None:
    data = resp.json()
    if data.get('status') != 200 or data.get('code') != 0:
        logging.warning("Quark API error: %s", data.get('message', 'unknown'))
        return None
    return data.get('data')


def _req(method: str, url: str, cookie: str = '', **kwargs) -> requests.Response:
    headers = dict(_JSON_HEADERS)
    if cookie:
        headers['Cookie'] = cookie
    kwargs['headers'] = headers
    kwargs['proxies'] = get_proxies()
    resp = requests.request(method, url, timeout=15, **kwargs)
    resp.raise_for_status()
    return resp


def get_quark_stoken(share_url: str, cookie: str = '') -> tuple[str, str]:
    parsed = urlparse(share_url)
    pwd_id = parsed.path.rstrip('/').rsplit('/', 1)[-1]
    url = (
        'https://drive-h.quark.cn/1/clouddrive/share/sharepage/token'
        '?pr=ucpro&fr=pc&uc_param_str='
    )
    resp = _req('POST', url, cookie, json={'pwd_id': pwd_id})
    data = _api_data(resp)
    if data is None or 'stoken' not in data:
        raise RuntimeError(f"\u83b7\u53d6 Quark stoken \u5931\u8d25: {share_url}")
    return data['stoken'], pwd_id


def get_quark_file_list(pdir_fid: str, stoken: str, pwd_id: str, cookie: str = '') -> list[dict]:
    url = 'https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail'
    params = {
        'pr': 'ucpro', 'fr': 'pc', 'ver': '2',
        'pwd_id': pwd_id, 'stoken': stoken, 'pdir_fid': pdir_fid,
        'force': '0', '_page': '1', '_size': '50',
        '_fetch_banner': '1', '_fetch_share': '1',
        'fetch_relate_conversation': '1', '_fetch_total': '1',
        '_sort': 'file_type:asc,file_name:asc',
    }
    headers = dict(_HEADERS)
    if cookie:
        headers['Cookie'] = cookie
    resp = requests.get(url, headers=headers, params=params, timeout=15, proxies=get_proxies())
    resp.raise_for_status()
    data = _api_data(resp)
    return data.get('list', []) if data else []


def find_audio_file(pdir_fid: str, stoken: str, pwd_id: str, song_title: str,
                    cookie: str = '', _depth: int = 0) -> dict | None:
    if _depth > MAX_RECURSION:
        logging.warning("Quark \u76ee\u5f55\u9012\u5f52\u8d85\u9650\uff0c\u8df3\u8fc7: %s", pdir_fid)
        return None
    items = get_quark_file_list(pdir_fid, stoken, pwd_id, cookie)
    title_lower = song_title.lower()
    for item in items:
        if item.get('dir'):
            result = find_audio_file(item['fid'], stoken, pwd_id,
                                     song_title, cookie, _depth + 1)
            if result:
                return result
        else:
            file_name = item.get('file_name', '')
            name_lower = file_name.lower()
            if title_lower in name_lower:
                ext = '.' + file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''
                if ext in AUDIO_EXTS:
                    return {
                        'fid': item['fid'],
                        'file_name': file_name,
                        'size': item.get('size', 0),
                        'share_fid_token': item.get('share_fid_token', ''),
                    }
    return None


def save_share_file(fid: str, token: str, stoken: str, pwd_id: str, cookie: str) -> str:
    url = (
        'https://drive-h.quark.cn/1/clouddrive/share/sharepage/save'
        '?pr=ucpro&fr=pc&uc_param_str='
    )
    body = {
        'fid_list': [fid],
        'fid_token_list': [token],
        'to_pdir_fid': '0',
        'pwd_id': pwd_id,
        'stoken': stoken,
        'pdir_fid': '0',
        'pdir_save_all': False,
        'exclude_fids': [],
        'scene': 'link',
    }
    resp = _req('POST', url, cookie, json=body)
    data = _api_data(resp)
    if data is None:
        raise RuntimeError("\u8f6c\u5b58\u5230\u8d26\u53f7\u5931\u8d25")
    task_id = data.get('task_id', '')
    if not task_id:
        raise RuntimeError("\u8f6c\u5b58\u4efb\u52a1ID\u4e3a\u7a7a")
    return task_id


def poll_save_task(task_id: str, cookie: str) -> str:
    for i in range(TASK_POLL_MAX):
        url = (
            f'https://drive-h.quark.cn/1/clouddrive/task'
            f'?pr=ucpro&fr=pc&uc_param_str=&task_id={task_id}&retry_index={i}'
        )
        resp = _req('GET', url, cookie)
        data = _api_data(resp)
        if data is None:
            time.sleep(1)
            continue
        status = data.get('status', -1)
        if status == 2:
            save_as = data.get('save_as', {}) or {}
            fids = save_as.get('save_as_top_fids', [])
            if fids:
                return fids[0]
            raise RuntimeError("\u8f6c\u5b58\u5b8c\u6210\u4f46\u672a\u627e\u5230\u6587\u4ef6ID")
        elif status == 3:
            raise RuntimeError("\u8f6c\u5b58\u4efb\u52a1\u5931\u8d25")
        time.sleep(1)
    raise RuntimeError("\u8f6c\u5b58\u4efb\u52a1\u8d85\u65f6")


def get_account_download_url(account_fid: str, cookie: str) -> str:
    url = 'https://drive-pc.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=pc&uc_param_str='
    resp = _req('POST', url, cookie, json={'fids': [account_fid]})
    data = _api_data(resp)
    if data is None or not isinstance(data, list) or not data:
        raise RuntimeError("\u83b7\u53d6\u4e0b\u8f7d\u94fe\u63a5\u5931\u8d25")
    download_url = data[0].get('download_url', '')
    if not download_url:
        raise RuntimeError("\u4e0b\u8f7d\u94fe\u63a5\u4e3a\u7a7a")
    return download_url


def download_from_quark(share_url: str, song_title: str, save_path: str, cookie: str,
                        progress_callback=None) -> tuple[bool, str, str]:
    try:
        stoken, pwd_id = get_quark_stoken(share_url, cookie)
        audio = find_audio_file('0', stoken, pwd_id, song_title, cookie)
        if audio is None:
            return False, '', '\u672a\u627e\u5230\u5339\u914d\u7684\u97f3\u9891\u6587\u4ef6'

        task_id = save_share_file(audio['fid'], audio.get('share_fid_token', ''),
                                  stoken, pwd_id, cookie)
        account_fid = poll_save_task(task_id, cookie)
        download_url = get_account_download_url(account_fid, cookie)
        file_path = os.path.join(save_path, safe_filename(audio['file_name']))
        download_file(download_url, file_path, cookie, progress_callback)
        return True, file_path, ''
    except Exception as e:
        return False, '', str(e)
