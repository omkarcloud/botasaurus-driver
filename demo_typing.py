#!/usr/bin/env python3
"""Gate for real key-event Element.send_keys. Run: python3 demo_typing.py

Exits non-zero on FAIL. SKIP (unreachable badssl host) is not a failure.
"""
import os
import socket
import string
import sys
import tempfile
import time
from pathlib import Path

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from botasaurus_driver import Driver

# Characters that are intentionally unmapped and go through Input.insertText.
INSERT_TEXT_CHARS = set('{}|:"<>?~\x0b\x0c')
BADSSL_HOST = "self-signed.badssl.com"
BADSSL_URL = "https://self-signed.badssl.com/"
SAMPLE = "A+b@c_D.e"
UNICODE_SAMPLE = "é中😀"

HARNESS_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>typing gate</title></head>
<body>
  <input id="type-input" autocomplete="off">
  <button id="space-btn" type="button">Go</button>
  <form id="type-form">
    <input id="form-input" autocomplete="off">
  </form>
  <div id="event-log" hidden></div>
  <script>
    window.__events = [];
    window.__submits = 0;
    window.__clicks = 0;

    function record(e) {
      window.__events.push({
        type: e.type,
        key: e.key,
        code: e.code,
        keyCode: e.keyCode,
        charCode: e.charCode,
        shiftKey: !!e.shiftKey
      });
    }

    ["keydown", "keypress", "keyup", "input", "beforeinput"].forEach(function (t) {
      document.addEventListener(t, record, true);
    });

    document.getElementById("type-form").addEventListener("submit", function (e) {
      e.preventDefault();
      window.__submits += 1;
    });
    document.getElementById("space-btn").addEventListener("click", function () {
      window.__clicks += 1;
    });

    window.__getEvents = function () {
      var out = window.__events.slice();
      window.__events = [];
      return out;
    };
    window.__reset = function () {
      window.__events = [];
      window.__submits = 0;
      window.__clicks = 0;
    };
  </script>
</body>
</html>
"""


class Skip(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def mapped_printable():
    return [c for c in string.printable if c not in INSERT_TEXT_CHARS]


def js(driver, expr):
    return driver.run_js("return " + expr)


def get_events(driver):
    ev = js(driver, "window.__getEvents()")
    return ev if ev else []


def key_seq(events):
    return [
        (e.get("type"), e.get("key"))
        for e in events
        if e.get("type") in ("keydown", "keypress", "keyup")
    ]


def key_edges(events):
    return [e for e in events if e.get("type") in ("keydown", "keyup")]


def reset_capture(driver):
    driver.run_js("window.__reset();")


def type_in(driver, selector, text):
    el = driver.select(selector)
    check(el is not None, "missing element " + selector)
    el.type(text)
    return el


def clear_value(driver, selector):
    el = driver.select(selector)
    check(el is not None, "missing element " + selector)
    el.run_js("(el) => { el.value = ''; }")
    return el


def load_harness(driver, uri):
    driver.get(uri)
    reset_capture(driver)


def test_ordering_and_count(driver):
    clear_value(driver, "#type-input")
    reset_capture(driver)
    type_in(driver, "#type-input", "ab")
    got = key_seq(get_events(driver))
    want = [
        ("keydown", "a"),
        ("keypress", "a"),
        ("keyup", "a"),
        ("keydown", "b"),
        ("keypress", "b"),
        ("keyup", "b"),
    ]
    check(got == want, "ordering/count for 'ab': got %r want %r" % (got, want))


def test_code_never_empty(driver):
    for ch in mapped_printable():
        el = clear_value(driver, "#type-input")
        el.run_js("(el) => el.focus()")
        reset_capture(driver)
        el.type(ch)
        events = get_events(driver)
        edges = key_edges(events)
        check(
            edges,
            "mapped char %r produced no keydown/keyup (missing KEYBOARD_LAYOUT entry?)"
            % ch,
        )
        for e in edges:
            check(
                e.get("code"),
                "empty code for %r on %s (key=%r)"
                % (ch, e.get("type"), e.get("key")),
            )


def test_keycode_fidelity(driver):
    clear_value(driver, "#type-input")
    reset_capture(driver)
    type_in(driver, "#type-input", "a")
    events = get_events(driver)
    downs = [e for e in events if e.get("type") == "keydown" and e.get("key") == "a"]
    presses = [e for e in events if e.get("type") == "keypress" and e.get("key") == "a"]
    check(downs, "no keydown for 'a'")
    check(presses, "no keypress for 'a'")
    check(
        downs[0].get("keyCode") == 65,
        "keydown.keyCode for 'a' is %r want 65" % downs[0].get("keyCode"),
    )
    check(
        presses[0].get("keyCode") == 97,
        "keypress.keyCode for 'a' is %r want 97" % presses[0].get("keyCode"),
    )


def test_shift_state_and_pairing(driver):
    clear_value(driver, "#type-input")
    reset_capture(driver)
    type_in(driver, "#type-input", "@")
    events = [
        e
        for e in get_events(driver)
        if e.get("type") in ("keydown", "keypress", "keyup")
    ]
    shift_downs = [
        i
        for i, e in enumerate(events)
        if e.get("type") == "keydown" and e.get("key") == "Shift"
    ]
    at_idxs = [i for i, e in enumerate(events) if e.get("key") == "@"]
    check(shift_downs, "no Shift keydown before @")
    check(at_idxs, "no @ events")
    check(
        shift_downs[0] < at_idxs[0],
        "Shift keydown must precede @ (Shift at %s, @ at %s)"
        % (shift_downs[0], at_idxs[0]),
    )
    for e in (events[i] for i in at_idxs):
        check(e.get("shiftKey") is True, "@ event missing shiftKey: %r" % e)
        check(e.get("code") == "Digit2", "@ code is %r want Digit2" % e.get("code"))
        check(e.get("key") == "@", "@ key is %r" % e.get("key"))
    shift_events = [e for e in events if e.get("key") == "Shift"]
    ups = [e for e in shift_events if e.get("type") == "keyup"]
    downs = [e for e in shift_events if e.get("type") == "keydown"]
    check(ups, "no Shift keyup after @")
    check(ups[-1].get("shiftKey") is False, "Shift keyup should have shiftKey false")
    check(len(downs) == len(ups), "orphan Shift: %s downs, %s ups" % (len(downs), len(ups)))
    check(
        shift_events[-1].get("type") == "keyup",
        "last Shift event is %s, not keyup" % shift_events[-1].get("type"),
    )


def test_newline_contract(driver):
    for text in ("\n", "\r", "\r\n"):
        clear_value(driver, "#form-input")
        reset_capture(driver)
        type_in(driver, "#form-input", text)
        events = get_events(driver)
        downs = [
            e
            for e in events
            if e.get("type") == "keydown"
            and e.get("key") == "Enter"
            and e.get("code") == "Enter"
        ]
        submits = js(driver, "window.__submits")
        label = repr(text)
        check(len(downs) == 1, "%s: want 1 Enter keydown, got %s" % (label, len(downs)))
        check(submits == 1, "%s: want 1 form submit, got %r" % (label, submits))

    reset_capture(driver)
    type_in(driver, "#type-input", "\t")
    events = get_events(driver)
    tabs = [
        e
        for e in events
        if e.get("type") in ("keydown", "keyup") and e.get("key") == "Tab"
    ]
    check(tabs, "no Tab keydown/keyup")
    check(
        all(e.get("key") == "Tab" and e.get("code") == "Tab" for e in tabs),
        "Tab event key/code mismatch: %r" % tabs,
    )
    active = js(driver, "document.activeElement && document.activeElement.id")
    check(
        active and active != "type-input",
        "Tab did not move document.activeElement (still %r)" % active,
    )

    reset_capture(driver)
    type_in(driver, "#space-btn", " ")
    clicks = js(driver, "window.__clicks")
    check(clicks == 1, "space on button: want 1 click, got %r" % clicks)


def test_unicode_round_trip(driver):
    el = clear_value(driver, "#type-input")
    reset_capture(driver)
    el.type(UNICODE_SAMPLE)
    check(
        el.value == UNICODE_SAMPLE,
        "unicode value %r want %r" % (el.value, UNICODE_SAMPLE),
    )


def test_final_value(driver):
    el = clear_value(driver, "#type-input")
    reset_capture(driver)
    el.type(SAMPLE)
    check(el.value == SAMPLE, "final value %r want %r" % (el.value, SAMPLE))


def _badssl_reachable():
    try:
        socket.create_connection((BADSSL_HOST, 443), timeout=5).close()
        return True
    except OSError:
        return False


def test_bypass_insecure_connection_warning(driver):
    if not _badssl_reachable():
        raise Skip("%s unreachable" % BADSSL_URL)
    try:
        driver.get(BADSSL_URL, timeout=20)
    except Exception as e:
        raise Skip("could not open %s: %s" % (BADSSL_URL, e))
    driver.allow_insecure_connections()
    time.sleep(1.5)
    blob = " ".join(
        [
            str(driver.title or ""),
            str(driver.page_text or ""),
            str(js(driver, "location.hostname") or ""),
        ]
    ).lower()
    still_blocked = (
        "your connection is not private" in blob
        or "net::err_cert" in blob
        or "privacy error" in blob
    )
    check(not still_blocked, "still on certificate warning after bypass")
    check(
        "badssl" in blob or "self-signed" in blob,
        "bypass did not reach the badssl page (title/text=%r)" % blob[:200],
    )


HARNESS_TESTS = (
    test_ordering_and_count,
    test_code_never_empty,
    test_keycode_fidelity,
    test_shift_state_and_pairing,
    test_newline_contract,
    test_unicode_round_trip,
    test_final_value,
)


def main():
    html_path = None
    driver = None
    failed = 0
    fd, html_path = tempfile.mkstemp(suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(HARNESS_HTML)
        uri = Path(html_path).as_uri()
        driver = Driver(headless=True)

        results = []
        for fn in HARNESS_TESTS:
            load_harness(driver, uri)
            results.append(_run(fn, driver))
        results.append(_run(test_bypass_insecure_connection_warning, driver))

        for status, name, detail in results:
            if detail:
                print("%s %s: %s" % (status, name, detail))
            else:
                print("%s %s" % (status, name))
            if status == "FAIL":
                failed += 1
    finally:
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass
        if html_path and os.path.exists(html_path):
            os.remove(html_path)
    sys.exit(1 if failed else 0)


def _run(fn, driver):
    name = fn.__name__
    try:
        fn(driver)
        return ("PASS", name, "")
    except Skip as e:
        return ("SKIP", name, str(e))
    except Exception as e:
        return ("FAIL", name, str(e))


if __name__ == "__main__":
    main()
