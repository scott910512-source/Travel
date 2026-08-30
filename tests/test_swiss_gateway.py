# 스위스 인근 공항. 스위스 도착이 아니므로 절대 스위스 목록과 섞이면 안 된다.
import sys, os, json, io, tempfile
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

print("실제 config")
gw = S.swiss_gateways()
print("  ", {k: (v["city"], v["to"], v["train_hours"]) for k, v in gw.items()})
chk(len(gw) >= 3, "게이트웨이를 읽는다")
chk(all("train_hours" in v and "to" in v and "city" in v for v in gw.values()),
    "도착 도시·기차 시간이 전부 있다")
chk(not any(k in ("ZRH", "GVA", "BSL") for k in gw),
    "스위스 공항 자체는 게이트웨이가 아니다")

print("\n스캔 대상에 포함되는가")
w = S.load_watchlist()
codes = {t[1] for t in w}
chk(set(gw) <= codes, "게이트웨이가 관심 노선에 들어 있다 (매일 조회됨)")
chk(all(t[3] == "유럽" for t in w if t[1] in gw),
    "유럽 규칙으로 조회된다 (v3 왕복 · 장기 체류)")

print("\n스위스 목록과 섞이지 않는가")
chk(not (set(gw) & set(S.SWISS_NIGHTS.__class__ and
        {s[1] for s in S.SWISS})), "SWISS 상수에는 게이트웨이가 없다")

print("\n망가진 입력")
d = tempfile.mkdtemp(); p = os.path.join(d, "w.json")
json.dump({"routes": [
    {"from": "ICN", "to": "AAA", "city": "없는곳", "active": False,
     "swiss_gateway": {"to": "취리히", "train_hours": 1}},
    {"from": "ICN", "to": "BBB", "city": "게이트웨이아님", "active": True},
]}, io.open(p, "w", encoding="utf-8"), ensure_ascii=False)
S.WATCHLIST_CONFIG = p
g2 = S.swiss_gateways()
chk("AAA" not in g2, "active:false 는 제외")
chk("BBB" not in g2, "swiss_gateway 없는 노선은 제외")
S.WATCHLIST_CONFIG = "/nonexistent.json"
chk(S.swiss_gateways() == {}, "파일이 없어도 죽지 않는다")
sys.exit(0 if ok else 1)
