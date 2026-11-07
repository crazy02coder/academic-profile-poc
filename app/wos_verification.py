"""User-operated WoS verification on the collector's existing Playwright page.

Only screenshots and a small input vocabulary cross the socket. Pages, cookies,
challenge responses and navigation commands are never exported to the client.
"""
from __future__ import annotations

import asyncio
import json
import math
import secrets
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from starlette.websockets import WebSocketDisconnect

WAIT_SECONDS = 300
_TOP_HOSTS = {'webofscience.com', 'www.webofscience.com'}
_KEYS = {'Tab', 'Enter', 'Escape', 'Backspace', 'Delete', 'ArrowLeft', 'ArrowRight',
         'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown', 'Space', ' '}
_MESSAGES = {
    'cancelled': 'WoS doğrulaması iptal edildi.',
    'expired': 'WoS doğrulama süresi doldu. Tekrar tara ile yeniden deneyebilirsiniz.',
    'unsafe_navigation': 'Doğrulama sırasında izin verilmeyen bir sayfa açıldı.',
    'closed': 'WoS doğrulama sayfası kapandı.',
    'error': 'WoS doğrulaması tamamlanamadı.',
    'busy': 'Başka bir WoS doğrulaması kullanıcı yanıtını bekliyor.',
}


class VerificationUnavailable(Exception):
    def __init__(self, reason: str, message: str | None = None):
        self.reason = reason
        super().__init__(message or _MESSAGES.get(reason, _MESSAGES['error']))


@dataclass(eq=False)
class _Budget:
    timer: asyncio.Timeout
    remaining: float | None
    loop: asyncio.AbstractEventLoop


@dataclass(eq=False)
class _Challenge:
    page: object
    id: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    status: str = 'waiting'
    reason: str = ''
    title: str = 'Web of Science insan doğrulaması'
    host: str = 'www.webofscience.com'
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0
    width: int = 1280
    height: int = 720
    controller: object = None
    held: bool = False
    done: asyncio.Event = field(default_factory=asyncio.Event)
    io: asyncio.Lock = field(default_factory=asyncio.Lock)


_CHALLENGES: dict[str, _Challenge] = {}
_BUDGETS: set[_Budget] = set()
_REGISTER = asyncio.Lock()


def _waiting() -> bool:
    return any(item.status == 'waiting' for item in _CHALLENGES.values())


def _pause_budgets() -> None:
    for budget in tuple(_BUDGETS):
        deadline = budget.timer.when()
        if deadline is not None and not budget.timer.expired():
            budget.remaining = max(0, deadline - budget.loop.time())
            budget.timer.reschedule(None)


def _resume_budgets() -> None:
    if _waiting():
        return
    for budget in tuple(_BUDGETS):
        if budget.remaining is not None and budget.timer.when() is None and not budget.timer.expired():
            budget.timer.reschedule(budget.loop.time() + budget.remaining)


@asynccontextmanager
async def time_budget(seconds: float | None):
    """An asyncio.timeout whose remaining time pauses during human verification."""
    loop = asyncio.get_running_loop()
    remaining = None if seconds is None else max(0.0, float(seconds))
    async with asyncio.timeout(None) as timer:
        budget = _Budget(timer, remaining, loop)
        _BUDGETS.add(budget)
        if remaining is not None and not _waiting():
            timer.reschedule(loop.time() + remaining)
        try:
            yield
        finally:
            _BUDGETS.discard(budget)


def _allowed_url(url: str, *, frame: bool = False) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        return (parsed.scheme == 'https' and not parsed.username and not parsed.password
                and parsed.port in (None, 443)
                and (host in _TOP_HOSTS or (frame and (host == 'hcaptcha.com' or host.endswith('.hcaptcha.com')))))
    except (TypeError, ValueError):
        return False


def same_origin(connection, *, required: bool = True) -> bool:
    """Compare browser Origin with this exact HTTP/WS authority; no localhost aliases."""
    origin = connection.headers.get('origin')
    if not origin:
        return not required
    try:
        source = urlsplit(origin)
        target = urlsplit(str(connection.url))
        target_scheme = {'ws': 'http', 'wss': 'https'}.get(target.scheme, target.scheme)
        if (source.scheme not in ('http', 'https') or source.scheme != target_scheme
                or source.username or source.password or source.path not in ('', '/')
                or source.query or source.fragment):
            return False
        default = 443 if source.scheme == 'https' else 80
        return bool(source.hostname) and source.hostname == target.hostname and (source.port or default) == (target.port or default)
    except (TypeError, ValueError):
        return False


_INSPECT = """() => {
  const visible = el => {
    if (!el) return false;
    if (el.checkVisibility && !el.checkVisibility({checkOpacity:true, checkVisibilityCSS:true})) return false;
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width >= 2 && r.height >= 2 && s.display !== 'none' && s.visibility !== 'hidden'
      && Number(s.opacity) !== 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  };
  const frames = [...document.querySelectorAll('iframe')].filter(visible);
  const captcha = frames.some(el => {
    try { const u = new URL(el.src, location.href), r = el.getBoundingClientRect();
      return (u.hostname === 'hcaptcha.com' || u.hostname.endsWith('.hcaptcha.com')) && r.width >= 30 && r.height >= 30;
    } catch { return false; }
  });
  const content = [...document.querySelectorAll('[data-ta^="FullRTa-fullRecordtitle-"], input[data-ta="search-criteria-input"], a[data-ta="summary-record-title-link"], button[data-ta="run-search"]')].some(visible);
  const body = document.body?.innerText || '';
  const emptyResults = /\\/wos\\/[^/]+\\/(summary|search)/.test(location.pathname)
    && /no results found|no records found|found no results|did not return any results|no matching records/i.test(body);
  const gateHeading = [...document.querySelectorAll('h1,h2,h3,[role="dialog"],p,div,span')].some(el => {
    const text = (el.innerText || '').trim();
    return text.length <= 300 && /^(please\\s+)?(verify|confirm) (that )?you are (a )?human\\b|^human verification\\b/i.test(text) && visible(el);
  });
  const gate = captcha || gateHeading || (!content && /verify (that )?you are (a )?human|confirm (that )?you are (a )?human|human verification/i.test(body));
  return {gate, content:content || emptyResults, width:innerWidth, height:innerHeight,
    frames:frames.filter(el => el.getAttribute('src')).map(el => el.src).filter(src => src !== 'about:blank')};
}"""


async def _inspect(page) -> dict:
    async with asyncio.timeout(4):
        return await page.evaluate(_INSPECT)


def _check_page(item: _Challenge) -> None:
    if item.page.is_closed():
        raise VerificationUnavailable('closed')
    if not _allowed_url(item.page.url):
        raise VerificationUnavailable('unsafe_navigation')


def _check_state(item: _Challenge, state: dict) -> None:
    item.width = max(1, int(state['width']))
    item.height = max(1, int(state['height']))


def _finish(item: _Challenge, status: str, reason: str = '') -> None:
    if item.status != 'waiting':
        return
    item.status, item.reason = status, reason
    item.done.set()


async def _release(item: _Challenge) -> None:
    if item.held:
        item.held = False
        with suppress(Exception):
            async with asyncio.timeout(2):
                await item.page.mouse.up(button='left')


def get_active() -> dict:
    return {'items': [{key: getattr(item, key) for key in
                      ('id', 'status', 'title', 'host', 'created_at', 'expires_at', 'width', 'height')}
                     for item in _CHALLENGES.values() if item.status == 'waiting']}


async def handle(page) -> bool:
    """Wait only for a visible gate; the collector continues on the same Page."""
    if not _allowed_url(page.url):
        return False
    try:
        state = await _inspect(page)
    except Exception:
        return False  # Navigation can replace the execution context between checks.
    if not state.get('gate'):
        return False
    async with _REGISTER:
        existing = next((c for c in _CHALLENGES.values() if c.status == 'waiting'), None)
        if existing is not None and existing.page is not page:
            raise VerificationUnavailable('busy')
        if existing is None:
            item = _Challenge(page=page, host=urlsplit(page.url).hostname or '')
            item.expires_at = item.created_at + WAIT_SECONDS
            _check_state(item, state)
            _CHALLENGES[item.id] = item
            _pause_budgets()
        else:
            item = existing
    if existing is not None:
        await item.done.wait()
        if item.status == 'solved':
            return True
        raise VerificationUnavailable(item.reason or 'error')

    async def navigation(route):
        request = route.request
        if request.is_navigation_request():
            main = request.frame == page.main_frame
            if not _allowed_url(request.url, frame=not main):
                if main:
                    _finish(item, 'error', 'unsafe_navigation')
                await route.abort()
                return
        await route.fallback()

    def frame_navigated(frame):
        if frame == page.main_frame and not _allowed_url(frame.url):
            _finish(item, 'error', 'unsafe_navigation')

    def page_closed():
        _finish(item, 'error', 'closed')

    async def popup_opened(popup):
        with suppress(Exception):
            await popup.close()

    routed = False
    deadline = asyncio.get_running_loop().time() + WAIT_SECONDS
    timer = asyncio.timeout_at(deadline)
    try:
        async with timer:
            await page.route('**/*', navigation)
            routed = True
            page.on('framenavigated', frame_navigated)
            page.on('close', page_closed)
            page.on('popup', popup_opened)
            stable, errors = 0, 0
            while item.status == 'waiting':
                if asyncio.get_running_loop().time() >= deadline:
                    _finish(item, 'expired', 'expired')
                    break
                try:
                    async with item.io:
                        _check_page(item)
                        current = await _inspect(page)
                        _check_page(item)
                        _check_state(item, current)
                    errors = 0
                    stable = stable + 1 if current.get('content') and not current.get('gate') else 0
                    if stable >= 2:
                        _finish(item, 'solved')
                        break
                except VerificationUnavailable as exc:
                    _finish(item, 'error', exc.reason)
                    break
                except Exception:
                    stable = 0
                    errors += 1
                    if errors >= 10:
                        _finish(item, 'error', 'error')
                        break
                with suppress(TimeoutError):
                    await asyncio.wait_for(item.done.wait(), timeout=min(.5, max(.01, deadline - asyncio.get_running_loop().time())))
        if item.status != 'solved':
            raise VerificationUnavailable(item.reason or 'error')
        return True
    except TimeoutError as exc:
        reason = 'expired' if timer.expired() else 'error'
        _finish(item, 'expired' if reason == 'expired' else 'error', reason)
        raise VerificationUnavailable(reason) from exc
    except asyncio.CancelledError:
        _finish(item, 'cancelled', 'cancelled')
        raise
    except VerificationUnavailable:
        raise
    except Exception as exc:
        _finish(item, 'error', 'error')
        raise VerificationUnavailable('error') from exc
    finally:
        if item.status == 'waiting':
            _finish(item, 'error', 'error')
        try:
            async with item.io:
                await _release(item)
        finally:
            for event, callback in (('framenavigated', frame_navigated), ('close', page_closed), ('popup', popup_opened)):
                with suppress(Exception):
                    page.remove_listener(event, callback)
            try:
                if routed:
                    with suppress(Exception):
                        async with asyncio.timeout(3):
                            await page.unroute('**/*', navigation)
            finally:
                _CHALLENGES.pop(item.id, None)
                _resume_budgets()


def _number(value, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('invalid numeric input')
    return float(value)


_HIT = """({x,y,keyboard}) => {
  const el = keyboard ? document.activeElement : document.elementFromPoint(x,y);
  if (!el || el.tagName !== 'IFRAME') return true;
  try {
    const src = el.getAttribute('src');
    if (!src || src === 'about:blank') return true;
    const u = new URL(src, location.href);
    return u.protocol === 'https:' && (!u.port || u.port === '443') && !u.username && !u.password
      && (['webofscience.com','www.webofscience.com','hcaptcha.com'].includes(u.hostname) || u.hostname.endsWith('.hcaptcha.com'));
  } catch { return false; }
}"""


async def _input(item: _Challenge, payload: dict) -> None:
    kind = payload.get('type')
    if kind == 'cancel':
        if set(payload) != {'type'}:
            raise ValueError('invalid cancel input')
        _finish(item, 'cancelled', 'cancelled')
        return
    async with item.io:
        if item.status != 'waiting':
            return
        _check_page(item)
        async with asyncio.timeout(4):
            if kind == 'release':
                if set(payload) != {'type'}:
                    raise ValueError('invalid release input')
                await _release(item)
                return
            if kind in ('pointer', 'wheel'):
                allowed = {'type', 'x', 'y', 'action', 'button'} if kind == 'pointer' else {'type', 'x', 'y', 'deltaX', 'deltaY'}
                if set(payload) - allowed:
                    raise ValueError('unexpected input fields')
                x = min(item.width - 1, _number(payload.get('x'), 0, 1) * item.width)
                y = min(item.height - 1, _number(payload.get('y'), 0, 1) * item.height)
                if not await item.page.evaluate(_HIT, {'x': x, 'y': y, 'keyboard': False}):
                    raise VerificationUnavailable('unsafe_navigation')
                if kind == 'pointer':
                    action = payload.get('action')
                    if action not in ('down', 'move', 'up') or payload.get('button', 0) != 0 or isinstance(payload.get('button'), bool):
                        raise ValueError('invalid pointer action')
                    await item.page.mouse.move(x, y)
                    if action == 'down' and not item.held:
                        item.held = True
                        await item.page.mouse.down(button='left')
                    elif action == 'up':
                        await _release(item)
                else:
                    dx = _number(payload.get('deltaX', 0), -2000, 2000)
                    dy = _number(payload.get('deltaY', 0), -2000, 2000)
                    await item.page.mouse.move(x, y)
                    await item.page.mouse.wheel(dx, dy)
            elif kind in ('key', 'text'):
                field_name = 'key' if kind == 'key' else 'text'
                value = payload.get(field_name)
                if set(payload) != {'type', field_name} or not isinstance(value, str):
                    raise ValueError('invalid keyboard input')
                if kind == 'key' and value not in _KEYS:
                    raise ValueError('unsupported key')
                if kind == 'text' and (not 1 <= len(value) <= 256 or not value.isprintable()):
                    raise ValueError('invalid text input')
                if not await item.page.evaluate(_HIT, {'x': 0, 'y': 0, 'keyboard': True}):
                    raise VerificationUnavailable('unsafe_navigation')
                if kind == 'key':
                    await item.page.keyboard.press('Space' if value == ' ' else value)
                else:
                    await item.page.keyboard.insert_text(value)
            else:
                raise ValueError('unknown input type')


async def stream(websocket, challenge_id: str) -> None:
    if not same_origin(websocket):
        await websocket.close(code=4403)
        return
    item = _CHALLENGES.get(challenge_id)
    if item is None or item.status != 'waiting':
        await websocket.accept()
        await websocket.close(code=4404)
        return
    if item.controller is not None:
        await websocket.accept()
        await websocket.send_json({'type': 'busy', 'message': 'Bu doğrulama başka bir pencerede açık.'})
        await websocket.close(code=4409)
        return
    lease = object()
    item.controller = lease
    send_lock = asyncio.Lock()
    tasks = []

    async def send_json(value):
        async with send_lock:
            async with asyncio.timeout(3):
                await websocket.send_json(value)

    async def frames():
        previous_size = (item.width, item.height)
        while item.status == 'waiting':
            started = asyncio.get_running_loop().time()
            try:
                async with item.io:
                    _check_page(item)
                    current = await _inspect(item.page)
                    _check_state(item, current)
                    async with asyncio.timeout(5):
                        jpeg = await item.page.screenshot(type='jpeg', quality=70, full_page=False, scale='css', timeout=4000)
                    _check_page(item)
            except VerificationUnavailable:
                raise
            except Exception:
                # Solving a gate normally destroys its execution context while
                # WoS navigates. The bounded owner monitor decides real failure.
                await asyncio.sleep(.5)
                continue
            if item.status != 'waiting':
                return
            if previous_size != (item.width, item.height):
                await send_json({'type': 'ready', 'id': item.id, 'width': item.width, 'height': item.height,
                                 'expires_at': item.expires_at})
                previous_size = (item.width, item.height)
            async with send_lock:
                async with asyncio.timeout(3):
                    await websocket.send_bytes(jpeg)
            await asyncio.sleep(max(0, .5 - (asyncio.get_running_loop().time() - started)))

    async def inputs():
        allowance, last = 60.0, asyncio.get_running_loop().time()
        while item.status == 'waiting':
            raw = await websocket.receive_text()
            if len(raw) > 4096:
                raise ValueError('input too large')
            now = asyncio.get_running_loop().time()
            allowance, last = min(60.0, allowance + (now - last) * 60), now
            if allowance < 1:
                raise ValueError('input rate exceeded')
            allowance -= 1
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError('invalid input object')
            await _input(item, payload)

    try:
        await websocket.accept()
        await send_json({'type': 'ready', 'id': item.id, 'width': item.width, 'height': item.height,
                         'expires_at': item.expires_at})
        tasks = [asyncio.create_task(frames()), asyncio.create_task(inputs()), asyncio.create_task(item.done.wait())]
        completed, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if not item.done.is_set():
            for task in completed:
                task.result()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if item.done.is_set():
            await send_json({'type': 'finished', 'status': item.status,
                             'message': 'WoS doğrulaması tamamlandı.' if item.status == 'solved'
                             else _MESSAGES.get(item.reason, _MESSAGES['error'])})
    except VerificationUnavailable as exc:
        _finish(item, 'error', exc.reason)
        with suppress(Exception):
            await send_json({'type': 'finished', 'status': 'error', 'message': str(exc)})
    except (ValueError, KeyError, TypeError):
        with suppress(Exception):
            await websocket.close(code=4400)
    except (WebSocketDisconnect, RuntimeError, TimeoutError):
        pass  # A disconnected panel may reconnect without losing the challenge.
    except asyncio.CancelledError:
        raise
    except Exception:
        _finish(item, 'error', 'error')
        with suppress(Exception):
            await send_json({'type': 'finished', 'status': 'error', 'message': _MESSAGES['error']})
    finally:
        for task in tasks:
            task.cancel()
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
            async with item.io:
                await _release(item)
        finally:
            if item.controller is lease:
                item.controller = None
            with suppress(Exception):
                await websocket.close()


async def close() -> None:
    for item in tuple(_CHALLENGES.values()):
        _finish(item, 'cancelled', 'cancelled')
        async with item.io:
            await _release(item)
