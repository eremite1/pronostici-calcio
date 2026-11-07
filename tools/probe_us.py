import requests, re
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
for u, h in [("https://understat.com/getLeagueData/Serie_A/2026", {"X-Requested-With": "XMLHttpRequest", "Referer": "https://understat.com/league/Serie_A/2026"}),
             ("https://understat.com/league/Serie_A/2026", {}), ("https://understat.com/league/Serie_A", {}),
             ("https://understat.com/getLeagueData/Serie_A/2025", {"X-Requested-With": "XMLHttpRequest", "Referer": "https://understat.com/league/Serie_A/2025"})]:
    try:
        r = requests.get(u, headers={**H, **h}, timeout=40)
        print("==", u, r.status_code, len(r.content), r.headers.get("content-type"))
        t = r.text
        import html as H2; print(H2.unescape(re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",re.sub(r"<style.*?</style>|<script.*?</script>","",t,flags=re.S))))[:600])
        for v in ["datesData", "teamsData", "playersData", "getLeagueData", "cf-", "captcha", "Just a moment"]:
            if v in t: print("   contiene:", v)
        for s in re.findall(r'<script[^>]+src="([^"]+)"', t)[:10]: print("   script:", s)
    except Exception as e:
        print("ERR", u, e)
