# 관심 노선: 코드를 고치지 않고 목적지를 늘릴 수 있어야 한다.
import sys, os, json, io, tempfile
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

print("실제 config/watchlist.json")
real = S.load_watchlist()
print("  ", real)
chk(len(real) >= 1, "파일을 읽는다")
chk(all(len(t) == 4 for t in real), "(출발, 도착, 도시, 지역) 4-튜플")
chk(any(t[1] == "ZRH" and t[3] == "유럽" for t in real),
    "취리히가 유럽 규칙으로 등록돼 있다")

def with_file(obj):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "watchlist.json")
    json.dump(obj, io.open(p, "w", encoding="utf-8"), ensure_ascii=False)
    S.WATCHLIST_CONFIG = p
    return S.load_watchlist()

print("\n동작")
got = with_file({"routes": [
    {"from": "ICN", "to": "LIS", "city": "리스본", "region": "유럽"},
    {"from": "ICN", "to": "OLD", "city": "옛노선", "region": "유럽", "active": False},
    {"from": "ICN", "city": "잘못된항목", "region": "유럽"},
]})
chk(("ICN", "LIS", "리스본", "유럽") in got, "새 노선이 추가된다")
chk(not any(t[1] == "OLD" for t in got), "active:false 는 빠진다")
chk(len(got) == 1, "from/to 없는 항목은 건너뛴다 (죽지 않는다)")

print("\n망가진 입력")
S.WATCHLIST_CONFIG = "/nonexistent/watchlist.json"
chk(S.load_watchlist() == [], "파일이 없어도 빈 리스트 (스캔은 계속된다)")
d = tempfile.mkdtemp(); p = os.path.join(d, "w.json")
io.open(p, "w").write("{ 깨진 json")
S.WATCHLIST_CONFIG = p
chk(S.load_watchlist() == [], "JSON 이 깨져도 스캔이 죽지 않는다")
sys.exit(0 if ok else 1)
