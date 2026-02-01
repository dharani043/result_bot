import asyncio
from playwright.async_api import async_playwright
from config import PORTAL_URL

# limit concurrency here (3–5 recommended)
MAX_CONCURRENT = 3


async def fetch_single(page, roll, dob):
    roll = roll.upper().strip()

    try:
        await page.goto(PORTAL_URL, timeout=60000)

        await page.fill('input[name="Srollno"]', roll)
        await page.fill('input[name="Password"]', dob)
        await page.click('button[type="submit"]')

        await page.wait_for_timeout(3000)

        table = await page.query_selector("table")
        if table:
            rows = await page.query_selector_all("table tr")
            result = ""

            for row in rows[1:]:
                cols = await row.query_selector_all("td")
                if len(cols) >= 2:
                    subject = (await cols[0].inner_text()).strip()
                    marks = (await cols[1].inner_text()).strip()
                    result += f"{subject}: {marks}\n"

            return roll, result.strip()

        page_text = (await page.content()).lower()
        if any(k in page_text for k in ["database", "error", "not available", "connection"]):
            return roll, "DB_DOWN"

        return roll, None

    except Exception:
        return roll, None


async def fetch_results_batch(users):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"]
        )
        context = await browser.new_context()

        async def run_task(user):
            async with semaphore:
                try:
                    page = await context.new_page()
                    roll, res = await fetch_single(page, user["roll"], user["dob"])
                    await page.close()
                    results[roll] = res
                except Exception:
                    # Return safe default on any error
                    results[user["roll"]] = None

        tasks = [run_task(u) for u in users]
        await asyncio.gather(*tasks)

        await context.close()
        await browser.close()

    return results


def fetch_results(users):
    """
    Wrapper for bot.py (sync code)
    """
    return asyncio.run(fetch_results_batch(users))
