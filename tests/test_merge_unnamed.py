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

# 실제 스캔 데이터로 검증한다.
#
# 처음에는 "실데이터에서 건수가 줄어든다" 로 썼는데, 그 fix 가 배포된
# 뒤로는 deals.json 에 중복이 남아 있지 않아 테스트가 스스로 무효가 됐다.
# (350→350 으로 '실패') 지워지는 것을 확인할 게 아니라, 지워진 상태가
# 유지되는 것을 확인해야 한다.
import json, io
d = json.load(io.open('flight-deals/state/deals.json', encoding='utf-8'))
live = d['offers']
chk(len(S.merge_unnamed(live)) == len(live),
    f"이미 정리된 데이터를 또 돌려도 그대로다 (멱등, {len(live)}건)")

# 중복을 일부러 주입하면 정확히 그만큼만 지워진다
named = next(o for o in live if o.get('airline') not in (None, '?')
             and o.get('price_krw'))
ghost = dict(named, airline='?', id='ghost',
             price_krw=int(named['price_krw'] * 1.004))   # 0.4% 차이
got = S.merge_unnamed(live + [ghost])
chk(len(got) == len(live), "주입한 '?' 중복 1건이 지워진다")
chk(not any(o.get('id') == 'ghost' for o in got), "지워진 것이 그 유령 행이다")

far = dict(named, airline='?', id='far', price_krw=int(named['price_krw'] * 0.8))
got2 = S.merge_unnamed(live + [far])
chk(len(got2) == len(live) + 1, "20% 싼 '?' 는 다른 편이므로 남는다")
sys.exit(0 if ok else 1)
