/* 캐릭터 여행 모드의 벡터 캐릭터·소품. 손으로 그린 SVG 심볼이라 얼굴·옷·비율이 모든 동작에서 같다.
   기준(사용자 설명): 남 — 검은 가르마 머리, 듬직한 체격, 네이비 상의·검정 바지 / 여 — 앞머리 있는 단발, 검정 원피스·밝은 가디건.
   이미지 생성 도구가 없어 사진을 본뜬 그림이 아니라 특징을 옮긴 벡터 캐릭터다. 개인 사진은 배포 파일에 넣지 않는다.
   팔·다리는 따로 그룹이라 CSS 로 흔든다. 동작(class): walk · wait · look · eat · rest. 방향은 .flip. */
'use strict';
const TRIP_CHARS = {
  /* <defs> 안에 넣는다. use 로 여러 번 쓴다. 좌표계: 각 캐릭터 0 0 100 150, 발끝이 y=150. */
  defs: `
<symbol id="ch-man" viewBox="0 0 100 150" overflow="visible">
  <g class="body">
    <g class="leg leg-l"><rect x="36" y="98" width="14" height="40" rx="6" fill="#1C1C22"/><path d="M33 136h20v8a4 4 0 0 1-4 4H37a4 4 0 0 1-4-4z" fill="#F4F4F4"/><rect x="33" y="140" width="20" height="4" fill="#1C1C22"/></g>
    <g class="leg leg-r"><rect x="52" y="98" width="14" height="40" rx="6" fill="#1C1C22"/><path d="M49 136h20v8a4 4 0 0 1-4 4H53a4 4 0 0 1-4-4z" fill="#F4F4F4"/><rect x="49" y="140" width="20" height="4" fill="#1C1C22"/></g>
    <path d="M28 60h44a6 6 0 0 1 6 6v30a6 6 0 0 1-6 6H28a6 6 0 0 1-6-6V66a6 6 0 0 1 6-6z" fill="#1F2A5C"/>
    <path d="M42 60l8 9 8-9" fill="none" stroke="#141B3F" stroke-width="2.5"/><path d="M40 60h20l-10 6z" fill="#2E3B77"/>
    <g class="arm arm-l"><rect x="14" y="62" width="13" height="34" rx="6" fill="#1F2A5C"/><circle cx="20.5" cy="98" r="6" fill="#F3CDAA"/></g>
    <g class="arm arm-r"><rect x="73" y="62" width="13" height="34" rx="6" fill="#1F2A5C"/><circle cx="79.5" cy="98" r="6" fill="#F3CDAA"/><g class="prop prop-eat"><rect x="76" y="70" width="2" height="26" fill="#8B5A2B" transform="rotate(-25 77 83)"/><rect x="82" y="70" width="2" height="26" fill="#8B5A2B" transform="rotate(-18 83 83)"/></g></g>
  </g>
  <g class="head">
    <rect x="44" y="52" width="12" height="10" fill="#F3CDAA"/>
    <circle cx="50" cy="34" r="23" fill="#F3CDAA"/>
    <path d="M27 33c0-14 10-24 23-24s23 10 23 24c-3-6-8-10-14-11l-6 9c-4-3-8-6-9-10-7 1-13 4-17 12z" fill="#15151A"/>
    <path d="M52 15c6 0 12 3 16 8" fill="none" stroke="#2A2A33" stroke-width="2" stroke-linecap="round"/>
    <ellipse class="eye" cx="42" cy="36" rx="2.4" ry="3" fill="#2A2A33"/><ellipse class="eye" cx="58" cy="36" rx="2.4" ry="3" fill="#2A2A33"/>
    <path class="eye-shut" d="M39 36h6M55 36h6" stroke="#2A2A33" stroke-width="2" stroke-linecap="round" fill="none"/>
    <path d="M38 30h8M54 30h8" stroke="#2A2A33" stroke-width="1.8" stroke-linecap="round"/>
    <path class="mouth" d="M45 45q5 4 10 0" fill="none" stroke="#B0553A" stroke-width="1.8" stroke-linecap="round"/>
    <circle cx="36" cy="42" r="3" fill="#F7A8A0" opacity=".6"/><circle cx="64" cy="42" r="3" fill="#F7A8A0" opacity=".6"/>
  </g>
</symbol>
<symbol id="ch-woman" viewBox="0 0 100 150" overflow="visible">
  <g class="body">
    <g class="leg leg-l"><rect x="38" y="112" width="11" height="26" rx="5" fill="#F3CDAA"/><path d="M35 134h17v7a4 4 0 0 1-4 4h-9a4 4 0 0 1-4-4z" fill="#1C1C22"/><rect x="35" y="140" width="17" height="3" fill="#F4F4F4"/></g>
    <g class="leg leg-r"><rect x="51" y="112" width="11" height="26" rx="5" fill="#F3CDAA"/><path d="M48 134h17v7a4 4 0 0 1-4 4h-9a4 4 0 0 1-4-4z" fill="#1C1C22"/><rect x="48" y="140" width="17" height="3" fill="#F4F4F4"/></g>
    <path d="M34 62h32l10 54H24z" fill="#17171C"/>
    <path d="M30 62h9v52h-13z" fill="#CFE0F5"/><path d="M61 62h9l4 52H61z" fill="#CFE0F5"/>
    <g class="arm arm-l"><rect x="18" y="64" width="12" height="32" rx="6" fill="#CFE0F5"/><circle cx="24" cy="98" r="5.5" fill="#F3CDAA"/></g>
    <g class="arm arm-r"><rect x="70" y="64" width="12" height="32" rx="6" fill="#CFE0F5"/><circle cx="76" cy="98" r="5.5" fill="#F3CDAA"/><g class="prop prop-eat"><rect x="73" y="72" width="2" height="24" fill="#8B5A2B" transform="rotate(-25 74 84)"/><rect x="79" y="72" width="2" height="24" fill="#8B5A2B" transform="rotate(-18 80 84)"/></g></g>
    <path d="M34 66c-6 10-8 22-6 30" fill="none" stroke="#E4D2B8" stroke-width="2.5"/><rect x="24" y="92" width="12" height="9" rx="3" fill="#E4D2B8"/>
  </g>
  <g class="head">
    <rect x="45" y="54" width="10" height="10" fill="#F3CDAA"/>
    <circle cx="50" cy="36" r="21" fill="#F3CDAA"/>
    <path d="M29 38c0-14 9-23 21-23s21 9 21 23v14c0 4-3 6-6 6l-2-20H37l-2 20c-3 0-6-2-6-6z" fill="#1A1A20"/>
    <path d="M31 34c2-8 9-13 19-13s17 5 19 13c-5-3-11-4-19-4s-14 1-19 4z" fill="#1A1A20"/>
    <ellipse class="eye" cx="43" cy="39" rx="2.4" ry="3" fill="#2A2A33"/><ellipse class="eye" cx="57" cy="39" rx="2.4" ry="3" fill="#2A2A33"/>
    <path class="eye-shut" d="M40 39h6M54 39h6" stroke="#2A2A33" stroke-width="2" stroke-linecap="round" fill="none"/>
    <path class="mouth" d="M46 47q4 3 8 0" fill="none" stroke="#C0604A" stroke-width="1.8" stroke-linecap="round"/>
    <circle cx="37" cy="44" r="3" fill="#F7A8A0" opacity=".7"/><circle cx="63" cy="44" r="3" fill="#F7A8A0" opacity=".7"/>
  </g>
</symbol>
<symbol id="pr-car" viewBox="0 0 160 80" overflow="visible">
  <path d="M14 52h132a6 6 0 0 0 6-6V38a8 8 0 0 0-6-8l-30-4-18-16H60L40 26 16 30a8 8 0 0 0-8 8v8a6 6 0 0 0 6 6z" fill="#F4F4F6" stroke="#B9BEC9" stroke-width="2"/>
  <path d="M62 14h34l14 14H52z" fill="#BFE0F5"/><rect x="100" y="14" width="12" height="14" fill="#BFE0F5"/>
  <g class="wheel"><circle cx="42" cy="54" r="12" fill="#22242B"/><circle cx="42" cy="54" r="5" fill="#C9CCD6"/><path d="M42 44v20M32 54h20" stroke="#8C90A0" stroke-width="2"/></g>
  <g class="wheel"><circle cx="118" cy="54" r="12" fill="#22242B"/><circle cx="118" cy="54" r="5" fill="#C9CCD6"/><path d="M118 44v20M108 54h20" stroke="#8C90A0" stroke-width="2"/></g>
  <use href="#ch-man" x="58" y="-6" width="30" height="45"/><use href="#ch-woman" x="82" y="-3" width="27" height="40"/>
</symbol>
<symbol id="ic-airport" viewBox="0 0 40 40"><circle cx="20" cy="20" r="19" fill="#fff" stroke="#5B4BE0" stroke-width="2"/><path d="M20 8l3 9 9 3-9 3-3 9-3-9-9-3 9-3z" fill="#5B4BE0"/></symbol>
<symbol id="ic-hotel" viewBox="0 0 40 40"><circle cx="20" cy="20" r="19" fill="#fff" stroke="#0F9D58" stroke-width="2"/><rect x="11" y="12" width="18" height="18" rx="2" fill="#0F9D58"/><rect x="14" y="15" width="4" height="4" fill="#fff"/><rect x="22" y="15" width="4" height="4" fill="#fff"/><rect x="14" y="22" width="4" height="4" fill="#fff"/><rect x="22" y="22" width="4" height="8" fill="#fff"/></symbol>
<symbol id="ic-poi" viewBox="0 0 40 40"><circle cx="20" cy="20" r="19" fill="#fff" stroke="#5B4BE0" stroke-width="2"/><path d="M12 28l6-12 4 7 3-4 5 9z" fill="#5B4BE0"/><circle cx="26" cy="14" r="3" fill="#F5B301"/></symbol>
<symbol id="ic-meal" viewBox="0 0 40 40"><circle cx="20" cy="20" r="19" fill="#fff" stroke="#E0452C" stroke-width="2"/><path d="M10 19h20a10 10 0 0 1-20 0z" fill="#E0452C"/><path d="M13 13l14-4M14 16l12-3" stroke="#8B5A2B" stroke-width="2" stroke-linecap="round"/></symbol>
<symbol id="ic-rest" viewBox="0 0 40 40"><circle cx="20" cy="20" r="19" fill="#fff" stroke="#D07C12" stroke-width="2"/><path d="M11 16h16v7a6 6 0 0 1-6 6h-4a6 6 0 0 1-6-6z" fill="#D07C12"/><path d="M27 18h3a3 3 0 0 1 0 6h-3" fill="none" stroke="#D07C12" stroke-width="2"/><path d="M15 12q1-2 0-4M20 12q1-2 0-4" stroke="#D07C12" stroke-width="1.5" fill="none"/></symbol>
<symbol id="ic-custom" viewBox="0 0 40 40"><circle cx="20" cy="20" r="19" fill="#fff" stroke="#5B6072" stroke-width="2"/><circle cx="20" cy="17" r="6" fill="#5B6072"/><path d="M20 30l-6-9h12z" fill="#5B6072"/></symbol>
<symbol id="pr-palm" viewBox="0 0 60 80"><path d="M28 78c2-20 2-40 6-56" stroke="#8B5A2B" stroke-width="4" fill="none" stroke-linecap="round"/><path d="M34 22c-10-8-20-6-26 2 10-2 18 0 26 6zM34 22c8-10 18-10 26-4-9 0-17 3-24 10zM34 22c-2-12 4-20 12-22-4 6-6 12-6 20zM34 22c-12-2-20 4-24 12 8-4 16-6 24-4z" fill="#2E9E5B"/></symbol>`,
  /* 스타일: 동작별 팔다리. 캐릭터 g 에 class 를 준다. 움직임 줄이기 설정이면 흔들지 않는다. */
  css: `
.char .arm,.char .leg{transform-box:fill-box;transform-origin:50% 8%}
.char .prop-eat,.char .eye-shut{display:none}
.char.walk .leg-l{animation:tc-leg .55s ease-in-out infinite alternate}
.char.walk .leg-r{animation:tc-leg .55s ease-in-out infinite alternate-reverse}
.char.walk .arm-l{animation:tc-arm .55s ease-in-out infinite alternate-reverse}
.char.walk .arm-r{animation:tc-arm .55s ease-in-out infinite alternate}
.char.wait{animation:tc-bob 1.8s ease-in-out infinite}
.char.look .arm-r{transform:rotate(-150deg)}
.char.look .head{transform-box:fill-box;transform-origin:50% 90%;animation:tc-look 2.4s ease-in-out infinite}
.char.eat .prop-eat{display:block}
.char.eat .arm-r{animation:tc-eat 1s ease-in-out infinite}
.char.eat .mouth{animation:tc-mouth 1s ease-in-out infinite}
.char.rest .eye{display:none}.char.rest .eye-shut{display:block}
.char.rest{animation:tc-breathe 3s ease-in-out infinite}
.char.rest .arm-l,.char.rest .arm-r{transform:rotate(12deg)}
.pr-car .wheel{transform-box:fill-box;transform-origin:50% 50%;animation:tc-wheel .6s linear infinite}
@keyframes tc-leg{from{transform:rotate(-24deg)}to{transform:rotate(24deg)}}
@keyframes tc-arm{from{transform:rotate(-22deg)}to{transform:rotate(22deg)}}
@keyframes tc-bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-2px)}}
@keyframes tc-look{0%,100%{transform:rotate(-6deg)}50%{transform:rotate(6deg)}}
@keyframes tc-eat{0%,100%{transform:rotate(-70deg)}50%{transform:rotate(-95deg)}}
@keyframes tc-mouth{0%,100%{transform:scaleY(1)}50%{transform:scaleY(1.8)}}
@keyframes tc-breathe{0%,100%{transform:translateY(0)}50%{transform:translateY(1.5px)}}
@keyframes tc-wheel{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.char *,.char,.pr-car .wheel{animation:none!important}}`,
};
if (typeof module !== 'undefined') module.exports = TRIP_CHARS;
