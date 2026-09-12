"""위임 선택자에 빠진 data-* 가 없는지 검사한다.

클릭 핸들러에 분기는 있는데 closest() 선택자에 속성이 빠지면 버튼이
아무 반응도 하지 않는다. 화면에는 정상으로 보이므로 눈으로는 못 잡는다.
data-scope, data-longstops 가 실제로 그렇게 죽어 있었다.
"""
import os
import re
import sys

_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _R)
os.chdir(_R)

SRC = open("web/app.js", encoding="utf-8").read()


def click_body():
    i = SRC.index("document.addEventListener('click'")
    j = SRC.index("document.addEventListener('change'", i)
    return SRC[i:j]


def listed():
    m = re.search(r"const CLICK_ATTRS = \[(.*?)\];", SRC, re.S)
    assert m, "CLICK_ATTRS 목록을 찾지 못했다"
    return set(re.findall(r"'([a-z-]+)'", m.group(1)))


def test_selector_is_built_from_the_list():
    assert "closest(CLICK_SEL)" in SRC, \
        "선택자를 손으로 이어 붙이지 말고 CLICK_ATTRS 에서 만들어라"


def test_every_handled_attr_is_selectable():
    body = click_body()
    used = set(re.findall(r"(?:getAttribute|hasAttribute)\('data-([a-z-]+)'\)", body))
    # data-month-goto 는 이미 match 된 요소에서 다시 읽는 보조 플래그다.
    used -= {"month-goto"}
    missing = sorted(used - listed())
    assert not missing, f"핸들러는 읽는데 CLICK_ATTRS 에 없다: {missing}"


def test_every_rendered_attr_is_handled():
    """템플릿이 찍는 data-* 인데 아무도 안 읽는 것 = 죽은 버튼."""
    body = click_body()
    ch = SRC[SRC.index("document.addEventListener('change'"):]
    read = set(re.findall(r"(?:getAttribute|hasAttribute)\('data-([a-z-]+)'\)", body + ch))
    rendered = set(re.findall(r'data-([a-z-]+)="', SRC))
    # 표시용/빌드용 속성은 클릭 대상이 아니다.
    rendered -= {"build", "month-goto"}
    # CLICK_ATTRS 정의문 자체는 렌더가 아니다.
    dead = sorted(a for a in rendered - read if f"data-{a}=" in SRC)
    assert not dead, f"화면에 찍히는데 아무도 안 읽는다 (죽은 버튼): {dead}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
