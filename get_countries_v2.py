import asyncio
import json
from playwright.async_api import async_playwright

import os
COOKIES_PATH = os.path.join(os.path.dirname(__file__), 'diandian_cookies.json')

async def extract_countries():
    with open(COOKIES_PATH, 'r') as f:
        cookies_data = json.load(f)
    
    cookies = []
    if isinstance(cookies_data, dict):
        cookies = [{"name": k, "value": v, "domain": ".diandian.com", "path": "/"} for k, v in cookies_data.items()]
    else:
        cookies = cookies_data

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(cookies)
        page = await context.new_page()
        
        url = "https://app.diandian.com/app/53u5u6xw9779mt7/ios?market=1&country=24&system=4&id=6754280964&n=JuJuBit"
        print(f"Navigating to {url}")
        await page.goto(url, wait_until="networkidle")
        
        # 截个图看下页面，确认选择器的位置
        await page.screenshot(path="jujubit_page.png")
        
        # 根据用户截图，国家选择器在面包屑位置
        # 点击 "中国" 这个 span
        try:
            # 找到包含 "中国" 的 span 并点击
            await page.click("span:has-text('中国')")
            await asyncio.sleep(2)
            
            # 点击 "在架地区(172)"
            await page.click("text=在架地区")
            await asyncio.sleep(1)
            
            # 提取国家名称和 ID
            # 这里的元素通常是 Nuxt/ElementUI 渲染的
            # 我们直接从 DOM 中提取
            countries_data = await page.evaluate('''() => {
                const results = [];
                // 查找弹窗中的所有国家项
                // 观察点点数据的结构，国家项通常有特定的 class
                const items = document.querySelectorAll('.el-dialog .common-item, .el-dialog .country-item');
                items.forEach(item => {
                    // 获取文字和可能的 data-id 或 value 属性
                    const name = item.innerText.trim();
                    // 有些是通过点击事件传递 ID 的，我们尝试找其属性
                    const id = item.getAttribute('data-id') || item.getAttribute('value') || 'unknown';
                    results.push({name, id});
                });
                return results;
            }''')
            
            if not countries_data:
                # 尝试另一种方式：解析 window.__NUXT__ 中的 country 列表
                # 刚才在 HTML 里看到了 countrySelectAreaMap
                print("No countries found in DOM, taking screenshot...")
                await page.screenshot(path="debug_modal.png")
            else:
                print(json.dumps(countries_data, ensure_ascii=False, indent=2))
            
        except Exception as e:
            print(f"Error during extraction: {e}")
            await page.screenshot(path="error_state.png")
            
        await browser.close()

asyncio.run(extract_countries())
