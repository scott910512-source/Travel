# 항공사명을 안 주는 엔드포인트의 '?' 행이 같은 편의 실제 항공사 행과
# 겹치면 한 편이 두 줄이 된다. 화면 중복보다 나쁜 건 표본 수가 부풀어
# 평균가와 신뢰도가 틀어지는 것이다.
import sys, os
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S

def mk(air, price, dep="ICN", arr="ZRH", d0="2026-10-29", d1="2026-11-08", stops=1):
    return {"airline": air, "price_krw": price, "dep": dep, "arr": arr,
            "depart_date": d0, "return_date": d1, "stops": stops,
            "id": f"{air}-{price}"}

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

print("검사")
# 실측 그대로: '?' 844,492 와 EY 845,617 (차이 0.13%)
got = S.merge_unnamed([mk("?", 844492), mk("EY", 845617)])
chk(len(got) == 1 and got[0]["airline"] == "EY",
    "값이 거의 같으면 '?' 를 버리고 항공사명 있는 쪽을 남긴다")
chk(got[0]["price_krw"] == 845617,
    "필드를 섞지 않는다 — 싼 값 + 항공사명 조합을 지어내지 않는다")

# 진짜 다른 편 (실측 21% 차이) 은 살려야 한다
got = S.merge_unnamed([mk("ZE", 172427), mk("?", 218703), mk("RF", 218994)])
chk(len(got) == 2 and {o["airline"] for o in got} == {"ZE", "RF"},
    "값이 크게 다른 '?' 는 다른 편이므로 남긴다")

# 일정이 다르면 겹치는 게 아니다
got = S.merge_unnamed([mk("?", 845000, d1="2026-11-09"), mk("EY", 845617)])
chk(len(got) == 2, "귀국일이 다르면 별개")
got = S.merge_unnamed([mk("?", 845000, stops=2), mk("EY", 845617)])
chk(len(got) == 2, "환승 횟수가 다르면 별개")
got = S.merge_unnamed([mk("?", 845000, dep="PUS"), mk("EY", 845617)])
chk(len(got) == 2, "출발지가 다르면 별개")

# 비교 대상이 없으면 '?' 도 그대로 남는다 (유일한 데이터일 수 있다)
got = S.merge_unnamed([mk("?", 844492)])
chk(len(got) == 1, "짝이 없는 '?' 는 버리지 않는다")

# 실제 스캔 데이터로 표본 부풀림이 실제로 줄어드는가
import json, io
d = json.load(io.open('flight-deals/state/deals.json', encoding='utf-8'))
before = d['offers']; after = S.merge_unnamed(before)
chk(len(after) < len(before), f"실데이터에서 중복이 줄어든다 ({len(before)}→{len(after)})")
sw_b = sum(1 for o in before if o['arr'] in ('ZRH', 'GVA', 'BSL'))
sw_a = sum(1 for o in after if o['arr'] in ('ZRH', 'GVA', 'BSL'))
chk(sw_a < sw_b, f"스위스 표본이 실제 편 수로 줄어든다 ({sw_b}→{sw_a})")
sys.exit(0 if ok else 1)
