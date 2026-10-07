import os, asyncio, random, logging, string as _string, math, time, json
from typing import Optional, Callable, Awaitable
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext, Locator
from temp_mail import TempMail
from database import save_account, get_account_with_credits, mark_used, mark_banned
from proxy_manager import ProxyManager, load_proxy_list, COOLDOWN_SECONDS
from playwright_turnstile import solve_turnstile
import aiohttp

log = logging.getLogger("creator")
HIGGS = "https://higgsfield.ai"
SIGNUP = HIGGS + "/"
LOGIN = HIGGS + "/login"
CREATE = HIGGS + "/create"
GENJUTSU = HIGGS + "/genjutsu"
DEBUG_DIR = Path(os.getenv("DEBUG_DIR", "/tmp/debug"))
DEBUG_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR = Path(os.getenv("VIDEO_DIR", "/tmp/videos"))
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
PROXY_LIST = [p.strip() for p in os.getenv("PROXY_LIST", "").split(",") if p.strip()]
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
RUN_TIMEOUT = int(os.getenv("RUN_TIMEOUT", "900"))
PEAK_API_KEY = os.getenv("PEAK_API_KEY", "")

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--excludeSwitches=enable-automation",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-features=TranslateUI",
    "--renderer-process-limit=2",
    "--js-flags=--max-old-space-size=256",
]

MIN_ACTION_DELAY = float(os.getenv("MIN_ACTION_DELAY", "0.5"))
MAX_ACTION_DELAY = float(os.getenv("MAX_ACTION_DELAY", "2.0"))
STEALTH_MODE = False
PROXY_POOL = ProxyManager(load_proxy_list())
GLOBAL_ACCOUNT_DELAY = float(os.getenv("GLOBAL_ACCOUNT_DELAY", "450"))
_last_account_time = 0.0

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]
TIMEZONES = ["America/New_York","America/Los_Angeles","America/Chicago","Europe/London","Europe/Berlin","Asia/Tokyo"]
LANGUAGES_LIST = [["en-US","en"],["en-GB","en"],["en-AU","en"],["en-CA","en"]]
RESOLUTIONS = [{"width":1920,"height":1080},{"width":1440,"height":900},{"width":1536,"height":864}]
PLATFORMS = ["MacIntel","Win32","Linux x86_64"]

class FingerprintRandomizer:
    def __init__(self, timezone_id: str = "America/New_York"):
        self.ua = random.choice(USER_AGENTS)
        self.timezone = timezone_id
        self.languages = random.choice(LANGUAGES_LIST)
        self.resolution = random.choice(RESOLUTIONS)
        self.platform = random.choice(PLATFORMS)
        self.hw_concurrency = random.choice([4, 8, 8, 12, 16])
        self.device_memory = random.choice([4, 8, 8, 16])
        self.canvas_noise = random.uniform(0.0001, 0.001)
        self.webgl_vendor = random.choice(["Google Inc. (Apple)","Google Inc. (Intel)","Google Inc. (NVIDIA)"])
        self.webgl_renderer = random.choice([
            "ANGLE (Apple, Apple M1, OpenGL 4.1)",
            "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics, OpenGL 4.1)",
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060, OpenGL 4.5)"])
        self.audio_noise = random.uniform(0.00001, 0.0001)

    def stealth_script(self) -> str:
        # Use string concatenation to avoid f-string issues with JS braces
        parts = []
        parts.append("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        parts.append("Object.defineProperty(navigator,'languages',{get:()=>" + str(self.languages) + "});")
        parts.append("Object.defineProperty(navigator,'platform',{get:()=>'" + self.platform + "'});")
        parts.append("Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>" + str(self.hw_concurrency) + "});")
        parts.append("Object.defineProperty(navigator,'deviceMemory',{get:()=>" + str(self.device_memory) + "});")
        parts.append("Object.defineProperty(navigator,'plugins',{get:()=>[{name:'Chrome PDF Plugin'},{name:'Chrome PDF Viewer'}]});")
        parts.append("Object.defineProperty(navigator,'doNotTrack',{get:()=>'1'});")
        parts.append("Object.defineProperty(navigator,'maxTouchPoints',{get:()=>0});")
        
        canvas_noise_val = int(self.canvas_noise * 255)
        parts.append("""
        const _td=HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL=function(...a){
            const c=this.getContext('2d');
            if(c){
                const d=c.getImageData(0,0,this.width,this.height);
                for(let i=0;i<d.data.length;i+=4)d.data[i]^=""" + str(canvas_noise_val) + """;
                c.putImageData(d,0,0)
            }
            return _td.apply(this,a)
        };""")
        
        parts.append("""
        const _gp=WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter=function(p){
            if(p===37445)return'""" + self.webgl_vendor + """';
            if(p===37446)return'""" + self.webgl_renderer + """';
            return _gp.call(this,p)
        };""")
        
        parts.append("""
        const _co=AudioContext.prototype.createOscillator;
        AudioContext.prototype.createOscillator=function(){
            const o=_co.call(this);
            const _cn=o.connect.bind(o);
            o.connect=function(d){
                if(d.gain)d.gain.value*=(1+""" + str(self.audio_noise) + """);
                return _cn(d)
            };
            return o
        };""")
        
        parts.append("window.chrome={runtime:{}};")
        
        parts.append("""
        const _q=navigator.permissions.query;
        navigator.permissions.query=function(p){
            if(p.name==='notifications')return Promise.resolve({state:'prompt'});
            return _q.call(this,p)
        };""")
        
        return "".join(parts)

class HumanInput:
    @staticmethod
    async def human_move(page, x, y, steps=25):
        cur = await page.evaluate("()=>({x:0,y:0})")
        cx, cy = cur["x"], cur["y"]
        c1x, c1y = cx + random.uniform(-50,50), cy + random.uniform(-50,50)
        c2x, c2y = x + random.uniform(-50,50), y + random.uniform(-50,50)
        for i in range(steps):
            t = i / steps
            px = ((1-t)**3)*cx + 3*((1-t)**2)*t*c1x + 3*(1-t)*(t**2)*c2x + (t**3)*x
            py = ((1-t)**3)*cy + 3*((1-t)**2)*t*c1y + 3*(1-t)*(t**2)*c2y + (t**3)*y
            await page.mouse.move(px, py)
            await asyncio.sleep(random.uniform(0.01, 0.05))

    @staticmethod
    async def human_click(page, selector):
        el = None
        try:
            el = page.locator(selector).first
            box = await el.bounding_box()
            if not box:
                await el.click()
                return
            tx = box["x"] + box["width"] * random.uniform(0.3, 0.7)
            ty = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            await HumanInput.human_move(page, tx, ty, steps=random.randint(15, 30))
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.mouse.click(tx, ty)
        except Exception:
            try:
                await el.click()
            except Exception:
                pass

    @staticmethod
    async def human_type(page, selector, text):
        try:
            el = page.locator(selector).first
            await el.click()
            await asyncio.sleep(random.uniform(0.2, 0.5))
            for char in text:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.08, 0.25))
        except Exception:
            try:
                await el.fill(text)
            except Exception:
                pass

async def human_delay(lo=None, hi=None):
    if lo is not None and hi is not None:
        await asyncio.sleep(random.uniform(lo, hi))
    else:
        await asyncio.sleep(random.uniform(MIN_ACTION_DELAY, MAX_ACTION_DELAY))

async def pick_proxy():
    return await PROXY_POOL.next()

async def global_account_delay():
    global _last_account_time
    if GLOBAL_ACCOUNT_DELAY > 0:
        elapsed = time.time() - _last_account_time
        if elapsed < GLOBAL_ACCOUNT_DELAY:
            wait = GLOBAL_ACCOUNT_DELAY - elapsed + random.uniform(0, 150)
            log.info("global account delay: sleeping %.0fs" % wait)
            await asyncio.sleep(wait)
    _last_account_time = time.time()

def random_password():
    return "".join(random.choices(_string.ascii_letters + _string.digits + "!@#$%", k=16))

def random_name():
    f = ["Alex","Jordan","Sam","Casey","Riley","Quinn","Avery","Drew"]
    l = ["Carter","Brooks","Reyes","Pierce","Hayes","Cole","Lane","Vega"]
    return random.choice(f), random.choice(l)

async def click_any(scope, selectors, timeout=15000):
    hi = HumanInput()
    for sel in selectors:
        try:
            loc = scope.locator(sel).first
            if await loc.wait_for(state="visible", timeout=timeout):
                await hi.human_click(scope, sel)
                return True
        except Exception:
            continue
    return False

async def fill_any(scope, value, selectors, timeout=15000):
    hi = HumanInput()
    for sel in selectors:
        try:
            loc = scope.locator(sel).first
            if await loc.wait_for(state="visible", timeout=timeout):
                await hi.human_type(scope, sel, value)
                return True
        except Exception:
            continue
    return False

async def wait_any(page, selectors, timeout=30000):
    for sel in selectors:
        try:
            if await page.locator(sel).first.wait_for(state="visible", timeout=timeout):
                return True
        except Exception:
            continue
    return False

async def detect_captcha(page):
    caps = ['iframe[src*="captcha"]', 'iframe[src*="hcaptcha"]', 'iframe[src*="recaptcha"]',
            'div:has-text("Verify you are human")', '#cf-challenge', '.cf-turnstile', '[data-sitekey]']
    for sel in caps:
        try:
            if await page.locator(sel).first.is_visible(timeout=500):
                return True
        except Exception:
            continue
    return False

async def _find_settings_scope(page):
    containers = ['[role="dialog"]', '[aria-modal="true"]', '.settings-panel',
                  '.modal', '[class*="settings" i]', 'main', 'body']
    for c in containers:
        try:
            loc = page.locator(c).first
            if await loc.wait_for(state="visible", timeout=2000):
                return loc
        except Exception:
            continue
    return page

async def select_menu_option(page, row_label, option_text, log_cb=None):
    scope = await _find_settings_scope(page)
    row_sels = ['button:has-text("%s")' % row_label, '[role="button"]:has-text("%s")' % row_label,
                'div:has-text("%s") >> nth=0' % row_label, 'text="%s"' % row_label]
    opened = await click_any(scope, row_sels, timeout=8000)
    if not opened and log_cb:
        await log_cb("warn", "could not open '%s' row" % row_label)
    await human_delay(0.4, 1.0)
    opt_sels = ['[role="option"]:has-text("%s")' % option_text, 'li:has-text("%s")' % option_text,
                'div[role="menuitem"]:has-text("%s")' % option_text, 'button:has-text("%s")' % option_text,
                'div:has-text("%s") >> nth=0' % option_text, 'text="%s"' % option_text]
    picked = await click_any(page, opt_sels, timeout=8000)
    if not picked and log_cb:
        await log_cb("warn", "could not pick '%s' from '%s'" % (option_text, row_label))
    return picked

async def ensure_toggle_on(page, label_text, log_cb=None):
    scope = await _find_settings_scope(page)
    sw_sels = ['div:has-text("%s") >> [role="switch"]' % label_text,
               'div:has-text("%s") >> button[role="switch"]' % label_text,
               'div:has-text("%s") >> [aria-checked]' % label_text,
               'div:has-text("%s") >> button[type="button"]:has(svg)' % label_text]
    for sel in sw_sels:
        try:
            sw = scope.locator(sel).first
            if not await sw.wait_for(state="visible", timeout=8000):
                continue
            checked = await sw.get_attribute("aria-checked")
            data_state = await sw.get_attribute("data-state")
            is_on = (checked == "true") or (data_state == "checked")
            if is_on:
                if log_cb:
                    await log_cb("info", "'%s' already ON" % label_text)
                return True
            await sw.click()
            await human_delay(0.3, 0.8)
            if log_cb:
                await log_cb("ok", "'%s' toggled ON" % label_text)
            return True
        except Exception:
            continue
    if log_cb:
        await log_cb("warn", "could not locate toggle '%s'" % label_text)
    return False

async def get_proxy_location(proxy_url):
    """Detect proxy location to set correct timezone and avoid fingerprint mismatch."""
    try:
        log.info("Detecting proxy location for: %s" % proxy_url)
        proxy_dict = {
            "http": proxy_url,
            "https": proxy_url
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get('https://ipinfo.io/json', proxy=proxy_dict, timeout=10) as resp:
                if resp.status != 200:
                    log.warning("ipinfo.io returned status %d" % resp.status)
                    return "America/New_York"
                data = await resp.json()
                country = data.get('country', 'US')
                log.info("Proxy detected as located in: %s" % country)
                
                if country == 'DE': return 'Europe/Berlin'
                if country == 'GB': return 'Europe/London'
                if country == 'CA': return 'America/Toronto'
                if country == 'FR': return 'Europe/Paris'
                if country == 'NL': return 'Europe/Amsterdam'
                if country == 'RU': return 'Europe/Moscow'
                if country == 'CN': return 'Asia/Shanghai'
                if country == 'JP': return 'Asia/Tokyo'
                if country == 'AU': return 'Australia/Sydney'
                if country == 'BR': return 'America/Sao_Paulo'
                if country == 'IN': return 'Asia/Kolkata'
                if country == 'KR': return 'Asia/Seoul'
                if country == 'SG': return 'Asia/Singapore'
                if country == 'HK': return 'Asia/Hong_Kong'
                if country == 'TW': return 'Asia/Taipei'
                if country == 'IT': return 'Europe/Rome'
                if country == 'ES': return 'Europe/Madrid'
                if country == 'MX': return 'America/Mexico_City'
                if country == 'AR': return 'America/Argentina/Buenos_Aires'
                if country == 'ZA': return 'Africa/Johannesburg'
                if country == 'SE': return 'Europe/Stockholm'
                if country == 'NO': return 'Europe/Oslo'
                if country == 'DK': return 'Europe/Copenhagen'
                if country == 'FI': return 'Europe/Helsinki'
                if country == 'PL': return 'Europe/Warsaw'
                if country == 'UA': return 'Europe/Kiev'
                if country == 'TR': return 'Europe/Istanbul'
                if country == 'IL': return 'Asia/Jerusalem'
                if country == 'AE': return 'Asia/Dubai'
                if country == 'SA': return 'Asia/Riyadh'
                if country == 'EG': return 'Africa/Cairo'
                if country == 'NG': return 'Africa/Lagos'
                if country == 'KE': return 'Africa/Nairobi'
                if country == 'MA': return 'Africa/Casablanca'
                if country == 'TH': return 'Asia/Bangkok'
                if country == 'VN': return 'Asia/Ho_Chi_Minh'
                if country == 'PH': return 'Asia/Manila'
                if country == 'ID': return 'Asia/Jakarta'
                if country == 'MY': return 'Asia/Kuala_Lumpur'
                if country == 'NZ': return 'Pacific/Auckland'
                if country == 'CL': return 'America/Santiago'
                if country == 'CO': return 'America/Bogota'
                if country == 'PE': return 'America/Lima'
                if country == 'VE': return 'America/Caracas'
                if country == 'US': return 'America/New_York'
                
                log.warning("Country %s not explicitly mapped, defaulting to America/New_York" % country)
                return 'America/New_York'
    except Exception as e:
        log.error("Could not detect proxy location: %s" % str(e))
        log.warning("Defaulting to America/New_York. If proxy is not US-based, this may cause Cloudflare blocks.")
        return 'America/New_York'

class HiggsfieldCreator:
    def __init__(self, log_cb=None):
        self.log_cb = log_cb
        self.mail = TempMail()
        self.email = ""
        self.password = random_password()
        self.first, self.last = random_name()
        self.ctx = None
        self.page = None
        self.proxy = None
        self.reused_account = False
        self.fp = None
        self.hi = HumanInput()

    async def _log(self, level, msg):
        log.info("[%s] %s" % (level, msg))
        if self.log_cb:
            await self.log_cb(level, msg)

    async def _shot(self, tag):
        try:
            p = DEBUG_DIR / ("{}_{}.png".format(tag, random.randint(1000,9999)))
            await self.page.screenshot(path=str(p), full_page=True)
            await self._log("info", "debug screenshot: %s" % p)
        except Exception:
            pass

    async def _detect_cloudflare(self):
        cf_sels = [
            'text="Checking your browser"',
            'text="Just a moment"',
            'text="Verifying you are human"',
            'text="Enable JavaScript and cookies to continue"',
            '#cf-challenge', '.cf-turnstile', '#challenge-stage',
            '#challenge-form', '#cf-please-wait', '#cf-wrapper',
            'iframe[src*="challenges.cloudflare.com"]',
            'script[src*="challenges.cloudflare.com"]',
        ]
        for sel in cf_sels:
            try:
                if await self.page.locator(sel).first.is_visible(timeout=1000):
                    return True
            except Exception:
                continue
        return False

    async def _diagnose_page(self, tag):
        try:
            title = await self.page.title()
            url = self.page.url
            n_inputs = await self.page.locator("input").count()
            n_iframes = await self.page.locator("iframe").count()
            n_textareas = await self.page.locator("textarea").count()
            body = await self.page.evaluate("() => document.body ? document.body.innerText.slice(0, 300) : 'BODY_NOT_FOUND'")
            await self._log(
                "info",
                "%s: url=%s title=%r inputs=%d textareas=%d iframes=%d" % (tag, url, title, n_inputs, n_textareas, n_iframes),
            )
            await self._log("info", "%s: body starts %r" % (tag, body))
        except Exception as exc:
            await self._log("warn", "%s: could not inspect page: %s" % (tag, str(exc)))

    async def _dismiss_cookie_banner(self):
        sels = [
            'button:has-text("Accept all")',
            'button:has-text("Accept All")',
            'button:has-text("Accept all cookies")',
            'button:has-text("Allow all")',
            '[role="button"]:has-text("Accept all")',
            '#onetrust-accept-btn-handler',
            'button:has-text("I agree")',
            'button:has-text("Got it")',
            'button:has-text("Accept")',
        ]
        for sel in sels:
            try:
                loc = self.page.locator(sel).first
                if await loc.is_visible(timeout=1500):
                    await loc.click()
                    await human_delay(0.6, 1.4)
                    await self._log("ok", "dismissed cookie banner (%s)" % sel)
                    return True
            except Exception:
                continue
        return False

    async def _human_scroll(self, scrolls=3):
        for _ in range(scrolls):
            await self.page.mouse.wheel(0, random.randint(100, 400))
            await asyncio.sleep(random.uniform(0.5, 2.0))
        await asyncio.sleep(random.uniform(0.5, 1.5))

    async def run(self, reference_path, prompt, image_paths=None):
        self._image_paths = image_paths or []
        try:
            return await asyncio.wait_for(
                self._run_with_retries(reference_path, prompt), timeout=RUN_TIMEOUT
            )
        except asyncio.TimeoutError:
            await self._cleanup()
            raise RuntimeError("generation exceeded %ds overall timeout" % RUN_TIMEOUT)

    async def _run_with_retries(self, reference_path, prompt):
        last_err = None
        for attempt in range(1, 4):
            try:
                await self._log("info", "attempt %d/3" % attempt)
                result = await self._attempt(reference_path, prompt)
                if self.proxy:
                    await PROXY_POOL.reset_failure(self.proxy)
                return result
            except Exception as e:
                last_err = e
                await self._log("warn", "attempt %d failed: %s" % (attempt, str(e)))
                if self.proxy and not self.reused_account:
                    await PROXY_POOL.record_failure(self.proxy)
                    proxy_part = self.proxy.split('@')[0] if '@' in self.proxy else 'unknown'
                    await self._log("info", "proxy %s@*** marked failed, will retry with different proxy" % proxy_part)
                if self.page:
                    await self._shot("fail_attempt%d" % attempt)
                await self._cleanup()
                backoff = min(60 * (2 ** (attempt - 1)), 180)
                await self._log("info", "backoff: sleeping %ds before retry" % backoff)
                await asyncio.sleep(backoff)
        await self._cleanup()
        raise RuntimeError("all 3 attempts failed: %s" % str(last_err))

    async def _attempt(self, reference_path, prompt):
        acct = await get_account_with_credits()
        if acct:
            self.email = acct["email"]
            self.password = acct["password"]
            self.proxy = acct.get("proxy")
            self.reused_account = True
            await self._log("info", "reusing account %s (proxy=%s)" % (self.email, self.proxy or 'none'))
        else:
            await global_account_delay()
            self.proxy = await pick_proxy()
            self.reused_account = False

        proxy_tz = "America/New_York"
        if self.proxy:
            proxy_tz = await get_proxy_location(self.proxy)
        
        await self._log("info", "launching browser (proxy=%s, pool=%d, tz=%s)" % ('yes' if self.proxy else 'no', PROXY_POOL.size, proxy_tz))
        
        self.fp = FingerprintRandomizer(timezone_id=proxy_tz)

        self._pw = await async_playwright().start()
        launch_args = {"headless": HEADLESS, "args": list(BROWSER_ARGS)}
        if self.proxy:
            launch_args["proxy"] = {"server": self.proxy}
        self.browser = await self._pw.chromium.launch(**launch_args)
        self.ctx = await self.browser.new_context(
            viewport=self.fp.resolution,
            user_agent=self.fp.ua,
            locale="en-US",
            timezone_id=self.fp.timezone,
            screen={"width": self.fp.resolution["width"], "height": self.fp.resolution["height"]})
        await self.ctx.add_init_script(self.fp.stealth_script())
        self.page = await self.ctx.new_page()

        if not self.reused_account:
            await self._create_account()
        await self._login()
        await self._run_genjutsu(reference_path, prompt)
        await mark_used(self.email, 0)
        await self._log("ok", "account %s marked used (credits=0)" % self.email)
        return await self._download_result()

    async def _create_account(self):
        self.email = await self.mail.create()
        await self._log("info", "temp inbox ready: %s" % self.email)
        try:
            await self.page.goto(SIGNUP, wait_until="domcontentloaded", timeout=180000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(random.uniform(3, 6))
        except Exception as e:
            await self._log("warn", "goto failed: %s" % str(e))
            raise

        if await self._detect_cloudflare():
            await self._log("warn", "Cloudflare challenge detected on signup page.")
            await self._shot("cloudflare_signup_detected")
            try:
                proxy_for_solver = self.proxy
                if proxy_for_solver and not proxy_for_solver.startswith("http"):
                    proxy_for_solver = "http://" + proxy_for_solver
                token = await solve_turnstile(
                    self.page,
                    api_key=PEAK_API_KEY,
                    proxy=proxy_for_solver
                )
                if token:
                    await self._log("ok", "Cloudflare Turnstile solved successfully on signup.")
                    await self.page.wait_for_timeout(5000)
                else:
                    raise RuntimeError("Peak returned no token for signup challenge.")
            except Exception as e:
                await self._shot("cloudflare_solve_failed_signup")
                raise RuntimeError("Failed to solve Cloudflare challenge on signup: %s" % str(e))
        else:
            await self._log("info", "No Cloudflare challenge detected on signup page. Proceeding.")

        await self._dismiss_cookie_banner()
        await self._log("info", "clicking Sign up button...")
        
        signup_clicked = await click_any(self.page, [
            'header button:has-text("Sign up")',
            'header a:has-text("Sign up")',
            'nav button:has-text("Sign up")',
            'nav a:has-text("Sign up")',
            'button:has-text("Sign up")',
            'a:has-text("Sign up")',
            'text="Sign up"'
        ], timeout=10000)
        
        if not signup_clicked:
             if "login" in self.page.url:
                 await self._log("info", "On login page, attempting to find signup link...")
        
        await human_delay(1, 2)
        
        if await self._detect_cloudflare():
             await self._shot("cloudflare_signup_post_click")
             raise RuntimeError("Cloudflare challenge appeared after button click.")

        await fill_any(self.page, self.first, ['input[name="firstName"]', 'input[name="name"]',
            'input[placeholder*="first name" i]', 'input[placeholder*="name" i]'])
        await fill_any(self.page, self.last, ['input[name="lastName"]', 'input[placeholder*="last name" i]'])
        await human_delay()
        ok = await fill_any(self.page, self.email, ['input[type="email"]', 'input[name="email"]',
            'input[placeholder*="mail" i]', 'input[placeholder*="email" i]'])
        if not ok:
            if await self._dismiss_cookie_banner():
                ok = await fill_any(self.page, self.email, ['input[type="email"]', 'input[name="email"]',
                    'input[placeholder*="mail" i]', 'input[placeholder*="email" i]'])
        if not ok:
            await self._shot("signup_no_email_field")
            await self._diagnose_page("signup_no_email_field")
            raise RuntimeError("email field not found on signup (see diagnose line above)")
        await human_delay()
        ok = await fill_any(self.page, self.password, ['input[type="password"]', 'input[name="password"]',
            'input[placeholder*="password" i]'])
        if not ok:
            raise RuntimeError("password field not found on signup")
        await human_delay()
        await click_any(self.page, ['input[type="checkbox"]', '[role="checkbox"]'], timeout=3000)
        ok = await click_any(self.page, ['button[type="submit"]', 'button:has-text("Sign up")',
            'button:has-text("Create")', 'button:has-text("Register")', 'button:has-text("Continue")',
            'button:has-text("Get started")'])
        if not ok:
            raise RuntimeError("signup submit button not found")
        await self._log("info", "signup form submitted")
        await self._log("info", "waiting for verification email...")
        link = await self.mail.wait_for_link(log=lambda m: self._log("info", m))
        await self._log("ok", "verification link: %s" % link)
        await self.page.goto(link, wait_until="domcontentloaded", timeout=60000)
        await human_delay()
        if await detect_captcha(self.page):
            await self._shot("captcha_verify")
            raise RuntimeError("captcha on verification - needs a solver or manual solve")
        await self._log("ok", "email verified")
        await save_account(self.email, self.password, credits=1, proxy=self.proxy)
        await self._log("ok", "account saved (proxy bound: %s)" % (self.proxy or 'none'))
        if self.proxy:
            await PROXY_POOL.mark_used(self.proxy)

    async def _login(self):
        await self.page.goto(LOGIN, wait_until="domcontentloaded", timeout=60000)
        await human_delay()
        if await detect_captcha(self.page):
            await self._shot("captcha_login")
            raise RuntimeError("captcha on login - needs a solver or manual solve")
        await fill_any(self.page, self.email, ['input[type="email"]', 'input[name="email"]',
            'input[placeholder*="email" i]'])
        await human_delay()
        await fill_any(self.page, self.password, ['input[type="password"]', 'input[name="password"]'])
        await click_any(self.page, ['button[type="submit"]', 'button:has-text("Log in")',
            'button:has-text("Sign in")'])
        await self.page.wait_for_load_state("networkidle")
        if "/login" in self.page.url:
            if self.reused_account:
                await mark_banned(self.email)
                await self._log("warn", "account %s marked BANNED (login failed)" % self.email)
            raise RuntimeError("login failed - still on /login (bad creds or banned)")
        await self._log("ok", "logged in")

    async def _run_genjutsu(self, reference_path, prompt):
        resp = await self.page.goto(CREATE, wait_until="domcontentloaded", timeout=60000)
        if resp and resp.status >= 400:
            await self._log("info", "/create returned %d, falling back to /genjutsu" % resp.status)
            await self.page.goto(GENJUTSU, wait_until="domcontentloaded", timeout=60000)
        await human_delay()
        await self._log("info", "navigated to create interface (%s)" % self.page.url)
        if await detect_captcha(self.page):
            await self._shot("captcha_create")
            raise RuntimeError("captcha on create page - needs a solver or manual solve")
        await self._human_scroll(scrolls=random.randint(2, 4))
        await self._log("info", "selecting Model: Higgsfield Genjutsu")
        await select_menu_option(self.page, "Model", "Higgsfield Genjutsu", self._log)
        await human_delay()
        await self._log("info", "selecting Quality: 720p")
        await select_menu_option(self.page, "Quality", "720p", self._log)
        await human_delay()
        await self._log("info", "ensuring 'Use free gens' is ON")
        await ensure_toggle_on(self.page, "Use free gens", self._log)
        await human_delay()
        await self._log("info", "waiting before upload (human simulation)...")
        await asyncio.sleep(random.uniform(15, 40))
        file_inputs = self.page.locator('input[type="file"]')
        count = await file_inputs.count()
        await self._log("info", "found %d file input(s) on create page" % count)
        video_uploaded = False
        for i in range(count):
            inp = file_inputs.nth(i)
            accept = await inp.get_attribute("accept") or ""
            if "video" in accept or "video" not in accept:
                try:
                    await inp.set_input_files(reference_path)
                    await self._log("info", "reference video uploaded to input #%d" % i)
                    video_uploaded = True
                    break
                except Exception:
                    continue
        if not video_uploaded:
            await file_inputs.first.set_input_files(reference_path)
            await self._log("info", "reference video uploaded (fallback to first input)")
        await human_delay(1, 2)

        if self._image_paths:
            img_uploaded = False
            for i in range(count):
                inp = file_inputs.nth(i)
                accept = await inp.get_attribute("accept") or ""
                if "image" in accept:
                    try:
                        await inp.set_input_files([str(p) for p in self._image_paths])
                        await self._log("info", "%d reference image(s) uploaded to input #%d" % (len(self._image_paths), i))
                        img_uploaded = True
                        break
                    except Exception:
                        continue
            if not img_uploaded and count > 1:
                try:
                    await file_inputs.nth(1).set_input_files([str(p) for p in self._image_paths])
                    await self._log("info", "%d reference image(s) uploaded (input #1)" % len(self._image_paths))
                    img_uploaded = True
                except Exception:
                    pass
            if not img_uploaded:
                await self._log("warn", "could not find a separate image upload input — images may not have been uploaded")
        await human_delay(1, 2)
        ok = await fill_any(self.page, prompt, ['textarea[name="prompt"]',
            'textarea[placeholder*="prompt" i]', 'textarea[placeholder*="describe" i]',
            'textarea[placeholder*="scene" i]', 'textarea'])
        if not ok:
            raise RuntimeError("prompt textarea not found")
        await self._log("info", "prompt filled")
        await human_delay()
        ok = await click_any(self.page, ['button:has-text("Generate")', 'button:has-text("Create")',
            'button:has-text("Render")', 'button[type="submit"]', 'button:has-text("Make")'])
        if not ok:
            raise RuntimeError("generate button not found")
        await self._log("ok", "generation triggered")
        await self._log("info", "waiting for generation to complete...")
        done = await wait_any(self.page, ['video[src]', 'a[download]', 'button:has-text("Download")',
            'button:has-text("Save")', 'button:has-text("Download video")'], timeout=300000)
        if not done:
            raise RuntimeError("generation did not complete in time")
        await self._log("ok", "generation complete")

    async def _download_result(self):
        out = VIDEO_DIR / ("genjutsu_%d.mp4" % random.randint(10000,99999))
        try:
            async with self.page.expect_download(timeout=60000) as dl_info:
                ok = await click_any(self.page, ['a[download]', 'button:has-text("Download")',
                    'button:has-text("Save video")', 'button:has-text("Download video")'])
                if not ok:
                    raise RuntimeError("no download button")
            download = await dl_info.value
            await download.save_as(str(out))
            await self._log("ok", "video saved: %s" % out.name)
        except Exception:
            src = await self.page.locator('video').first.get_attribute("src")
            if not src:
                raise RuntimeError("could not locate result video")
            url = src if src.startswith("http") else HIGGS + src
            resp = await self.page.request.get(url)
            if resp.ok:
                out.write_bytes(await resp.body())
                await self._log("ok", "video fetched via src: %s" % out.name)
            else:
                raise RuntimeError("video fetch failed: HTTP %d" % resp.status)
        return out

    async def _cleanup(self):
        try:
            if self.ctx:
                await self.ctx.close()
            if getattr(self, "browser", None):
                await self.browser.close()
            if getattr(self, "_pw", None):
                await self._pw.stop()
        except Exception:
            pass
        await self.mail.close()
        self.ctx = self.page = None
        if hasattr(self, "browser"):
            self.browser = None
        if hasattr(self, "_pw"):
            self._pw = None
