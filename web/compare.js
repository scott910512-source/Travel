/* Side-by-side travel decisions. All prices and labels use the same app helpers. */
'use strict';
const TravelCompare = {
  create(d) {
    const { esc, won, effective, accessOf, depCity, leaveOf, whenLine, stopTxt, durTxt } = d;
    const buttonHTML = o => `<button class="compare-pick" data-compare="${esc(o.id)}"
      aria-pressed="${d.ids().includes(o.id)}" ${!d.ids().includes(o.id) && d.ids().length >= 3 ? 'disabled' : ''}
      aria-label="${esc(depCity(o.dep))} → ${esc(o.city)} ${esc(whenLine(o))} 비교 담기">
      ${d.ids().includes(o.id) ? '✓ 비교에 담음' : '＋ 비교 담기'}</button>`;
    function barHTML() {
      const n = d.ids().length;
      return n ? `<aside class="compare-bar" aria-label="선택한 항공권 비교">
        <span><b>${n}/3개 선택</b><small>${n === 3 ? '다른 후보는 담은 항공권을 뺀 뒤 추가' : '이동비 · 연차 · 환승 비교'}</small></span>
        <button class="btn-line" data-compare-clear>비우기</button>
        <button class="cta" data-view="compare" ${n < 2 ? 'disabled' : ''}>${n < 2 ? '1개 더 담기' : '비교하기'}</button>
      </aside>` : '';
    }
    function viewHTML() {
      const offers = d.offers();
      if (offers.length < 2) return `${d.header('항공권 비교', '같은 여행의 후보를 2~3개 담아 비교하세요', true)}
        <div class="wrap"><div class="note"><b>비교할 항공권을 더 담아 주세요</b>
        <p>목록이나 상세에서 ‘비교 담기’를 누르면 됩니다. 선택은 이 기기에 저장됩니다.</p></div>
        <button class="btn-go" data-tab="find">항공권 찾기 →</button></div>`;
      const min = Math.min(...offers.map(effective));
      const row = (label, cell) => `<tr><th scope="row">${label}</th>${offers.map(o => `<td>${cell(o)}</td>`).join('')}</tr>`;
      const sameTrip = offers.every(o => o.arr === offers[0].arr && o.depart_date === offers[0].depart_date
        && o.return_date === offers[0].return_date);
      return `${d.header('항공권 비교', '청주 근처에서 출발할 때, 돈과 연차를 함께 비교', true)}
      <div class="wrap">
        <p class="compare-hint">${sameTrip ? '같은 목적지·출발일·귀국일의 후보입니다.' : '목적지나 일정이 서로 다릅니다. 날짜를 함께 확인하세요.'}
        금액은 1인 왕복 기준입니다.</p>
        <div class="compare-scroll" tabindex="0" role="region" aria-label="항공권 비교표, 가로로 스크롤">
        <table class="compare-table"><caption class="sr">선택한 항공권의 일정과 비용 비교</caption>
        <thead><tr><th scope="col">비교 항목</th>${offers.map(o => `<th scope="col">
          <span>${esc(depCity(o.dep))} → ${esc(o.city)}</span>
          <button class="compare-remove" data-compare="${esc(o.id)}" aria-label="${esc(depCity(o.dep))} → ${esc(o.city)} 비교에서 제거">제거</button>
        </th>`).join('')}</tr></thead><tbody>
        ${row('예상 부담액', o => `<b class="compare-price">${won(effective(o))}원</b><small>${effective(o) === min ? '선택한 후보 중 최저' : `최저보다 +${won(effective(o) - min)}원`}</small>`)}
        ${row('항공권', o => `${won(o.price_krw)}원`)}
        ${row('공항 왕복 이동비', o => `${won(accessOf(o.dep))}원<small>설정한 1인 이동비</small>`)}
        ${row('일정', o => esc(whenLine(o)))}
        ${row('필요 연차', o => `${esc(leaveOf(o))}<small>${o.annual_leave_confirmed === true ? '앱의 근무일 계산 기준' : '한국 도착일 확인 필요'}</small>`)}
        ${row('환승', o => esc(stopTxt(o.stops)))}
        ${row('비행 소요', o => o.duration_min ? `${durTxt(o.duration_min)}<small>가는 편</small>` : o.duration_rt_min ? `${durTxt(o.duration_rt_min)}<small>왕복 합계</small>` : '미확인')}
        ${row('세금 · 수하물', o => esc(d.fareNote(o)))}
        ${row('가격 확인', o => d.freshBadge(o))}
        ${row('상세', o => `<button class="btn-line" data-open="${esc(o.id)}">일정·가격 보기</button>`)}
        </tbody></table></div>
        <p class="live-note">공항까지 이동시간·수속시간은 비행 소요에 포함되지 않습니다. 연차는 실제 근무표와 대조해 주세요.
        가격이 갱신되면 선택한 후보가 사라질 수 있습니다.</p>
        <button class="btn-line" data-view="settings">공항 이동비 조정</button>
      </div>`;
    }
    return { buttonHTML, barHTML, viewHTML };
  },
};
