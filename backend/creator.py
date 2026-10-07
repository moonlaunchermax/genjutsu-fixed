    async def _create_account(self):
        self.email = await self.mail.create()
        await self._log("info", f"temp inbox ready: {self.email}")
        
        try:
            await self.page.goto(SIGNUP, wait_until="domcontentloaded", timeout=180000)
            # Wait for network to settle - this is when Cloudflare often triggers
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(random.uniform(3, 6))  # Random delay to mimic human
        except Exception as e:
            await self._log("warn", f"goto failed: {e}")
            raise

        # FIX: Check for Cloudflare challenge *after* page load, not before
        if await self._detect_cloudflare():
            await self._log("warn", "Cloudflare challenge detected on signup page.")
            await self._shot("cloudflare_signup_detected")
            # Attempt to solve if detected
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
                raise RuntimeError(f"Failed to solve Cloudflare challenge on signup: {e}")
        else:
            await self._log("info", "No Cloudflare challenge detected on signup page. Proceeding.")

        await self._dismiss_cookie_banner()
        await self._log("info", "clicking Sign up button...")
        
        # Try to find signup button
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
             # If we are already on a signup form, this is fine. 
             # Check if we are on a login page instead and need to switch
             if "login" in self.page.url:
                 await self._log("info", "On login page, attempting to find signup link...")
                 # Logic to switch to signup if needed
                 pass
        
        await human_delay(1, 2)
        
        # Check again for challenges after clicking any buttons
        if await self._detect_cloudflare():
             await self._shot("cloudflare_signup_post_click")
             raise RuntimeError("Cloudflare challenge appeared after button click.")

        # Proceed with form filling...
        # [Rest of your form filling code remains the same]
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
        if not ok: raise RuntimeError("password field not found on signup")
        await human_delay()
        await click_any(self.page, ['input[type="checkbox"]', '[role="checkbox"]'], timeout=3000)
        ok = await click_any(self.page, ['button[type="submit"]', 'button:has-text("Sign up")',
            'button:has-text("Create")', 'button:has-text("Register")', 'button:has-text("Continue")',
            'button:has-text("Get started")'])
        if not ok: raise RuntimeError("signup submit button not found")
        await self._log("info", "signup form submitted")
        await self._log("info", "waiting for verification email...")
        link = await self.mail.wait_for_link(log=lambda m: self._log("info", m))
        await self._log("ok", f"verification link: {link}")
        await self.page.goto(link, wait_until="domcontentloaded", timeout=60000); await human_delay()
        if await detect_captcha(self.page):
            await self._shot("captcha_verify")
            raise RuntimeError("captcha on verification - needs a solver or manual solve")
        await self._log("ok", "email verified")
        await save_account(self.email, self.password, credits=1, proxy=self.proxy)
        await self._log("ok", f"account saved (proxy bound: {self.proxy or 'none'))")
        if self.proxy:
            await PROXY_POOL.mark_used(self.proxy)
