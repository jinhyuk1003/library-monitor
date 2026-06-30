# -*- coding: utf-8 -*-
import sys, json, urllib.request, urllib.parse
sys.stdout.reconfigure(encoding="utf-8")

API_KEY = "3af37144fb4779a0bfc82ab8500a9d491b6c03685bcae4849ae33bcc7862cb78"
encoded = urllib.parse.quote(API_KEY, safe="")
url = ("https://apis.data.go.kr/B551982/plr_v2/rlt_rdrm_info_v2"
       "?serviceKey=" + encoded +
       "&type=json&numOfRows=200&pageNo=1&stdgCd=4113000000")

with urllib.request.urlopen(
    urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
    timeout=15
) as r:
    data = json.loads(r.read().decode("utf-8"))

items = data.get("body", {}).get("item", [])
if isinstance(items, dict):
    items = [items]

libs = {}
for it in items:
    lid   = it.get("pblibId", "")
    lname = it.get("pblibNm", "")
    rname = it.get("rdrmNm", "")
    total = it.get("tseatCnt", "?")
    use   = it.get("rmndSeatCnt", "?")
    avail = it.get("useSeatCnt", "?")
    if lid not in libs:
        libs[lid] = {"name": lname, "rooms": []}
    libs[lid]["rooms"].append(
        "  [rdrmId?] " + rname +
        ": 총" + str(total) +
        " / 이용중" + str(use) +
        " / 잔여" + str(avail)
    )

print("성남시 공공도서관 목록 (" + str(len(libs)) + "곳)")
print("=" * 60)
for lid in sorted(libs.keys()):
    info = libs[lid]
    print("[" + lid + "] " + info["name"])
    for rm in info["rooms"]:
        print(rm)
    print()
