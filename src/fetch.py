"""Scaricamento dati dal web, con tentativi ripetuti e memoria locale (cache)."""
import json
import os
import time

import requests

from . import config

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"})

WARNINGS = []


def warn(msg):
    print("ATTENZIONE:", msg)
    if msg not in WARNINGS:
        WARNINGS.append(msg)


def get(url, headers=None, tries=3, timeout=30, allow_fail=True):
    last = None
    for i in range(tries):
        try:
            r = _session.get(url, headers=headers or {}, timeout=timeout)
            if r.status_code == 200 and r.content:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code in (403, 404):
                break
            if r.status_code in (202, 429, 503):  # il sito chiede di riprovare più tardi
                time.sleep(15 * (i + 1))
                continue
        except Exception as e:  # rete instabile
            last = str(e)
        time.sleep(2 * (i + 1))
    if not allow_fail:
        raise RuntimeError(f"Impossibile scaricare {url}: {last}")
    print(f"  fallito: {url} ({last})")
    return None


def get_text(url, headers=None, **kw):
    r = get(url, headers=headers, **kw)
    if r is None:
        return None
    return r.content.decode("utf-8-sig", errors="replace")


def get_json(url, headers=None, **kw):
    r = get(url, headers=headers, **kw)
    if r is None:
        return None
    try:
        return r.json()
    except Exception:
        return None


def cache_path(name):
    os.makedirs(config.CACHE, exist_ok=True)
    return os.path.join(config.CACHE, name)


def load_cache(name, default=None):
    p = cache_path(name)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_cache(name, obj):
    with open(cache_path(name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
