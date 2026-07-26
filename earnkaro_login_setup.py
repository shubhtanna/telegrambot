"""
earnkaro_login_setup.py
────────────────────────
Run this ONCE, on your own computer — NOT on Railway — because it needs
a visible browser window for you to actually log in through.

What it does:
  1. Opens a real Chrome window at the EarnKaro login page.
  2. You log in exactly as you normally would (phone/OTP, email/password,
     whatever EarnKaro asks for).
  3. Once you can see your logged-in dashboard, come back to this
     terminal and press Enter.
  4. It saves your session (cookies) to earnkaro_session.json.

Upload that file next to earnkaro_bot.py on your server (Railway).
EarnKaro sessions typically last for weeks — if earnkaro_bot.py's logs
start showing "0 cards found", that's the signal to run this again.

Setup (once):
    pip install playwright
    playwright install chromium
    python earnkaro_login_setup.py
"""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SESSION_FILE = Path(__file__).resolve().parent / "earnkaro_session.json"


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://earnkaro.com/login")

        print("A browser window has opened.")
        print("Log into EarnKaro exactly as you normally would.")
        input("Once you're logged in and can see your dashboard, press Enter here...")

        await context.storage_state(path=str(SESSION_FILE))
        print(f"Saved session to {SESSION_FILE}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())