import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
# Run only against the private demo instance; this saves its existing first name.
base_url = os.environ.get('AMPVE_BASE_URL', 'https://ampve.com').rstrip('/')
credential_path = os.environ.get('AMPVE_DEMO_CREDENTIALS', '/home/ampve/.config/ampve/demo-credentials.json')
creds = json.loads(Path(credential_path).read_text())['accounts'][0]
Path('.browser-tests').mkdir(exist_ok=True)
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 context=browser.new_context(viewport={'width':1440,'height':1100},extra_http_headers={})
 page=context.new_page()
 errors=[];page.on('pageerror',lambda e: errors.append(str(e)))
 page.goto(base_url+'/')
 page.screenshot(path='.browser-tests/landing-desktop.png',full_page=True)
 for width in [390,768,1440]:
  page.set_viewport_size({'width':width,'height':900})
  page.goto(base_url+'/')
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(width,'landing','overflow')
  page.screenshot(path=f'.browser-tests/landing-{width}.png',full_page=True)
 page.emulate_media(reduced_motion='reduce')
 page.goto(base_url+'/')
 assert page.locator('.hero-device-picture img').evaluate("el=>getComputedStyle(el).animationName")=='none'
 assert page.locator('.hero-ribbon').evaluate("el=>getComputedStyle(el).animationName")=='none'
 page.emulate_media(reduced_motion='no-preference')
 page.set_viewport_size({'width':1440,'height':1100})
 page.get_by_role('link',name='Sign in →',exact=True).click()
 page.get_by_label('Email address').fill(creds['email'])
 page.get_by_label('Password').fill(creds['password'])
 page.get_by_role('button',name='Sign in').click()
 page.wait_for_url('**/home/')
 page.screenshot(path='.browser-tests/home-desktop.png',full_page=True)
 for route in ['devices/','devices/add/','apps/','connections/','settings/','accounts/password/']:
  response=page.goto(base_url+'/'+route)
  assert response.status==200,(route,response.status)
  assert page.locator('h1').count()==1
 page.goto(base_url+'/settings/')
 page.get_by_label('First name').fill(creds['name'])
 page.get_by_role('button',name='Save changes').click()
 assert page.get_by_text('Your profile has been updated.').is_visible()
 for width in [390,768,1440]:
  page.set_viewport_size({'width':width,'height':900})
  for route in ['home/','devices/','devices/add/','apps/','connections/','settings/','accounts/password/']:
   page.goto(base_url+'/'+route)
   assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(width,route,'overflow')
  page.goto(base_url+'/home/')
  page.screenshot(path=f'.browser-tests/home-{width}.png',full_page=True)
  if width==390:
   page.locator('.menu-toggle').click()
   assert page.locator('.sidebar.open').is_visible()
   page.keyboard.press('Escape')
   assert page.locator('.menu-toggle').get_attribute('aria-expanded')=='false'
 page.set_viewport_size({'width':1440,'height':1100})
 page.get_by_role('button',name='Sign out',exact=True).click()
 page.wait_for_url(base_url+'/')
 page.goto(base_url+'/home/')
 page.wait_for_url('**/accounts/login/**')
 print('Browser smoke passed: landing motion/layout, login, pages, profile save, logout, mobile menu, 3 viewport widths. JS errors:',errors)
 assert not errors
 browser.close()
