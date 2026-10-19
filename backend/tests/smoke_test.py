import os
import os, sys
os.environ['RATE_LIMIT_AUTH'] = '25'
os.environ['FIREBASE_PROJECT_ID'] = 'demo-proj'
os.environ['FIREBASE_API_KEY'] = 'test-key'
os.environ['BROTHERSTRUST_DB'] = '/tmp/bt_final.db'
try: os.remove('/tmp/bt_final.db')
except FileNotFoundError: pass
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from urllib.parse import quote
import main as m

results = []
def check(name, cond):
    results.append(bool(cond)); print(('PASS' if cond else 'FAIL'), name)

with TestClient(m.app) as c:
    # security
    r = c.get('/api/health')
    check('security headers', r.headers.get('X-Content-Type-Options') == 'nosniff'
          and 'frame-ancestors' in r.headers.get('Content-Security-Policy', ''))
    r = c.get('/api/health', headers={'x-forwarded-proto': 'http', 'x-forwarded-host': 'example.com'}, follow_redirects=False)
    check('HTTPS redirect (308)', r.status_code == 308 and r.headers['location'].startswith('https://'))
    check('localhost exempt', c.get('/api/health', headers={'x-forwarded-proto': 'http', 'x-forwarded-host': 'localhost'}, follow_redirects=False).status_code == 200)

    # honeypot
    r = c.post('/auth/register', json={'email':'bot@spam.com','password':'x12345','full_name':'Bot','website':'http://spam'})
    check('honeypot: fake 200', r.status_code == 200 and r.json().get('access_token') == '')
    check('honeypot: no account', c.post('/auth/login', json={'email':'bot@spam.com','password':'x12345'}).status_code == 401)

    # register
    r = c.post('/auth/register', json={'email':'ada@example.com','password':'secret1','full_name':'Ada Obi','phone':'08012345678'})
    check('register', r.status_code == 200 and r.json()['access_token'])
    tok = r.json()['access_token']; H = {'Authorization': f'Bearer {tok}'}

    # validation
    check('phone validation 422', c.post('/bookings/car', headers=H, json={
        'city':'Lagos','category':'economy','pickup_date':'2026-10-20','return_date':'2026-10-21',
        'driver_name':'Ada Obi','driver_age':30,'contact_email':'ada@example.com','contact_phone':'abc'}).status_code == 422)

    # bookings
    f0 = c.get('/flights/search?origin=LOS&dest=ABV&date=2026-10-20').json()['flights'][0]
    fb = c.post('/bookings/flight', headers=H, json={
        'trip_type':'one_way','cabin':'economy',
        'legs':[{'origin':'LOS','dest':'ABV','date':'2026-10-20','flight_key':f0['flight_key']}],
        'passengers':[{'type':'adult','title':'Ms','first_name':'Ada','last_name':'Obi','dob':'1995-04-12'}],
        'contact_email':'ada@example.com','contact_phone':'+2348012345678'})
    check('flight book', fb.status_code == 201)
    check('mock pay settle', c.post('/payments/confirm', headers=H,
          json={'reference':fb.json()['reference'],'method':'card'}).json().get('booking_status') == 'confirmed')

    hs = c.get('/hotels/search?city=Lagos&checkin=2026-10-20&checkout=2026-10-22&rooms=1&guests=2')
    h = hs.json()['hotels'][0]; room = h['room_options'][0]
    hb = c.post('/bookings/hotel', headers=H, json={
        'hotel_id':h['id'],'room_type':room['type'],'checkin':'2026-10-20','checkout':'2026-10-22',
        'rooms':1,'guests':2,'guest_name':'Ada Obi','contact_email':'ada@example.com','contact_phone':'+2348012345678'})
    check('hotel book', hb.status_code == 201)

    can = c.post(f"/bookings/{hb.json()['reference']}/cancel", headers=H)
    check('cancel + refund', can.status_code == 200 and can.json()['refund_amount'] > 0)
    check('webhook tolerant', c.post('/payments/webhook', json={'event':'charge.success','data':{'reference':'x'}}).status_code == 200)

    # analytics
    for p in ['/', '/flights', '/flights']:
        c.post('/api/analytics', json={'kind': 'page_view', 'page': p})
    c.post('/api/analytics', json={'kind': 'payment_confirmed', 'page': '/pay/xx'})
    check('analytics beacon', c.post('/api/analytics', json={}).status_code == 200)

    # admin
    ar = c.post('/auth/login', json={'email':'admin@brotherstrusttravel.com','password':'BT#Admin1'})
    check('admin login', ar.status_code == 200)
    AH = {'Authorization': f"Bearer {ar.json()['access_token']}"}
    a = c.get('/admin/analytics', headers=AH).json()
    check('admin analytics', a['pageviews'] == 4 and a['events'].get('payment_confirmed') == 1 and len(a['top_pages']) == 2)
    ada = next(u for u in c.get('/admin/users', headers=AH).json() if u['email'] == 'ada@example.com')
    check('admin users enriched', ada['bookings'] == 2 and ada['spent'] > 0)
    check('admin stats', c.get('/admin/stats', headers=AH).status_code == 200)
    vb = c.post('/bookings/visa', headers=H, json={
        'country_code':'GB',
        'applicants':[{'full_name':'Ada Obi','passport_no':'A123456','dob':'1995-04-12'}],
        'contact_email':'ada@example.com','contact_phone':'+2348012345678'})
    check('visa book', vb.status_code == 201)
    check('registration fee 500', vb.json()['amount'] == 500)
    vref = vb.json()['reference']
    c.post('/payments/confirm', headers=H, json={'reference':vref,'method':'card'})
    r = c.post(f'/admin/bookings/{vref}/schedule', headers=AH, json={'date':'2026-11-05','time':'10:00','center':'UK Visas & Immigration - Accra'})
    check('admin schedules interview', r.status_code == 200 and r.json()['interview']['date'] == '2026-11-05')


    # pay-small-small installment flow
    kb = c.post('/bookings/car', headers=H, json={
        'city':'Abuja','category':'premium','pickup_date':'2026-10-24','return_date':'2026-10-25',
        'driver_name':'Ada Obi','driver_age':30,'contact_email':'ada@example.com','contact_phone':'+2348012345678'})
    kref = kb.json()['reference']
    r = c.post('/payments/installment', headers=H, json={'reference': kref})
    j = r.json()
    check('installment 30% accepted', r.status_code == 200 and j['first'] == round(kb.json()['amount'] * 0.3) and j['balance'] == kb.json()['amount'] - j['first'])
    check('still pending after 30%', c.get(f'/bookings/{kref}', headers=H).json()['status'] == 'pending')
    r = c.post('/payments/balance', headers=H, json={'reference': kref, 'method': 'card'})
    check('balance completes booking', r.status_code == 200 and r.json().get('booking_status') == 'confirmed')

    # pay-small-small cancellation refunds 30% of paid
    kb2 = c.post('/bookings/car', headers=H, json={
        'city':'Lagos','category':'luxury_suv','pickup_date':'2026-10-26','return_date':'2026-10-27',
        'driver_name':'Ada Obi','driver_age':30,'contact_email':'ada@example.com','contact_phone':'+2348012345678'})
    kref2 = kb2.json()['reference']
    first2 = c.post('/payments/installment', headers=H, json={'reference': kref2}).json()['first']
    r = c.post(f'/bookings/{kref2}/cancel', headers=H)
    check('installment cancel refunds 30%', r.status_code == 200 and r.json()['refund_amount'] == round(first2 * 0.3))

    # baggage fee
    fb2 = c.post('/bookings/flight', headers=H, json={
        'trip_type':'one_way','cabin':'economy','bags':2,
        'legs':[{'origin':'LOS','dest':'ABV','date':'2026-10-20','flight_key':f0['flight_key']}],
        'passengers':[{'type':'adult','title':'Ms','first_name':'Ada','last_name':'Obi','dob':'1995-04-12'}],
        'contact_email':'ada@example.com','contact_phone':'+2348012345678'})
    j2 = fb2.json()
    check('baggage fee added', j2['details']['bags_fee'] == 300 and j2['amount'] == j2['details']['fare'] + j2['details']['taxes'] + j2['details']['service_fee'] + 300)

    # office pay + admin confirm
    cb = c.post('/bookings/car', headers=H, json={
        'city':'Lagos','category':'economy','pickup_date':'2026-10-22','return_date':'2026-10-23',
        'driver_name':'Ada Obi','driver_age':30,'contact_email':'ada@example.com','contact_phone':'+2348012345678'})
    oref = cb.json()['reference']
    r = c.post('/payments/office', headers=H, json={'reference': oref})
    check('office reserve', r.status_code == 200 and r.json().get('reserved') and 'office' in r.json())
    check('office booking stays pending', c.get(f'/bookings/{oref}', headers=H).json()['status'] == 'pending')
    r = c.post(f'/admin/bookings/{oref}/confirm', headers=AH)
    check('admin confirm office pay', r.status_code == 200 and r.json().get('booking_status') == 'confirmed')

    # password reset
    r = c.post('/auth/forgot-password', json={'email':'ada@example.com'})
    link = r.json().get('dev_reset_link') or ''
    token = link.split('token=')[-1]
    check('forgot-password (existing)', r.status_code == 200 and len(token) > 20)
    check('forgot-password (unknown email)', c.post('/auth/forgot-password', json={'email':'ghost@nowhere.com'}).json().get('dev_reset_link') is None)
    check('reset bad token 400', c.post('/auth/reset-password', json={'token':'x'*30,'new_password':'newpass1'}).status_code == 400)
    check('reset password ok', c.post('/auth/reset-password', json={'token':token,'new_password':'newpass1'}).status_code == 200)
    check('login with new password', c.post('/auth/login', json={'email':'ada@example.com','password':'newpass1'}).status_code == 200)
    check('old password rejected', c.post('/auth/login', json={'email':'ada@example.com','password':'secret1'}).status_code == 401)
    tok = c.post('/auth/login', json={'email':'ada@example.com','password':'newpass1'}).json()['access_token']
    H = {'Authorization': f'Bearer {tok}'}

    # delete account
    check('delete wrong password 401', c.request('DELETE', '/auth/account', headers=H, json={'password':'nope'}).status_code == 401)
    check('delete account ok', c.request('DELETE', '/auth/account', headers=H, json={'password':'newpass1'}).status_code == 200)
    check('login blocked after delete', c.post('/auth/login', json={'email':'ada@example.com','password':'newpass1'}).status_code == 401)
    me = c.get('/auth/me', headers=H).json()
    check('data anonymised', me['email'].startswith('deleted_') and me['full_name'] == 'Deleted account')
    allb = c.get('/admin/bookings', headers=AH).json()
    check('booking history retained', any(b['email'] == 'deleted_2@removed.bt-travel' for b in allb))

    # firebase auth
    r = c.get('/auth/firebase-config')
    check('firebase config served', r.status_code == 200 and r.json()['apiKey'] == 'test-key' and r.json()['projectId'] == 'demo-proj')
    check('firebase bad token rejected', c.post('/auth/firebase', json={'id_token':'x'*40}).status_code in (401, 500))

    # static + rate limit last
    for asset in ['/robots.txt', '/sitemap.xml', '/assets/favicon-32.png', '/assets/og-image.png',
                  '/assets/apple-touch-icon.png', '/assets/favicon-16.png']:
        check(f'serve {asset}', c.get(asset).status_code == 200)
    check('cache header', c.get('/css/style.css').headers.get('Cache-Control', '').startswith('public'))
    check('SPA + fallback', "Brother'sTrust" in c.get('/').text and c.get('/nonexistent-page').status_code == 200)
    check('no secrets in HTML', 'BT#Admin1' not in c.get('/').text and 'SECRET' not in c.get('/').text)
    for i in range(25):
        c.post('/auth/login', json={'email':'nobody@nowhere.com','password':'wrong'})
    check('rate limit 429', c.post('/auth/login', json={'email':'nobody@nowhere.com','password':'wrong'}).status_code == 429)

print()
print('RESULT:', f'{sum(results)}/{len(results)} PASS' + (' — ALL GREEN' if all(results) else ' — FAILURES'))
