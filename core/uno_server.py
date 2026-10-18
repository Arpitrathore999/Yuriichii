"""HTTP/WebSocket server for Elara UNO Mini App. Uses aiohttp already in requirements."""
import asyncio, json, os, secrets, hmac, hashlib, urllib.parse
from pathlib import Path
from aiohttp import web, WSMsgType
from core.uno_engine import Game

ROOT=Path(__file__).resolve().parent.parent
WEB=ROOT/'uno_web'
ROOMS={}; LOCK=asyncio.Lock()
def _telegram_user(init_data):
    token=os.getenv('BOT_TOKEN') or os.getenv('API_TOKEN')
    if not init_data or not token: return None
    try:
        q=dict(urllib.parse.parse_qsl(init_data,keep_blank_values=True)); supplied=q.pop('hash',None)
        if not supplied: return None
        check='\n'.join(f'{k}={v}' for k,v in sorted(q.items()))
        secret=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
        expected=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,supplied): return None
        user=json.loads(q.get('user','{}')); uid=str(user['id']); name=(user.get('first_name','Player')+' '+user.get('last_name','')).strip()
        return uid,name[:40]
    except Exception: return None
async def _broadcast(room):
    dead=[]
    for ws,pid in list(room['sockets']):
        if ws.closed: dead.append((ws,pid)); continue
        try: await ws.send_json({'type':'state','state':room['game'].state_for(pid),'room':room['code'],'host':room['host']})
        except Exception: dead.append((ws,pid))
    for item in dead: room['sockets'].discard(item)
async def index(_): return web.FileResponse(WEB/'index.html')
async def health(_): return web.json_response({'ok':True,'service':'elara-uno'})
async def create_room(req):
    who=_telegram_user(req.headers.get('X-Telegram-Init-Data',''))
    if not who: return web.json_response({'error':'Open UNO from your Telegram bot so your identity can be verified.'},status=401)
    uid,name=who
    async with LOCK:
        code=secrets.token_hex(3).upper()
        game=Game(player_ids=[uid],names={uid:name})
        ROOMS[code]={'game':game,'host':uid,'sockets':set(),'created':asyncio.get_event_loop().time()}
    return web.json_response({'room':code,'name':name})
async def join_room(req):
    code=req.match_info['code'].upper(); who=_telegram_user(req.headers.get('X-Telegram-Init-Data',''))
    if not who: return web.json_response({'error':'Telegram identity could not be verified.'},status=401)
    uid,name=who
    async with LOCK:
        room=ROOMS.get(code)
        if not room: return web.json_response({'error':'Room not found.'},status=404)
        try: room['game'].add_player(uid,name)
        except ValueError as e: return web.json_response({'error':str(e)},status=400)
    await _broadcast(room); return web.json_response({'ok':True,'room':code})
async def room_info(req):
    code=req.match_info['code'].upper(); room=ROOMS.get(code)
    if not room: return web.json_response({'error':'Room not found.'},status=404)
    return web.json_response({'room':code,'players':[{'name':room['game'].names.get(p,p),'id':p} for p in room['game'].player_ids],'status':room['game'].status,'host':room['host']})
async def websocket(req):
    code=req.match_info['code'].upper(); who=_telegram_user(req.query.get('initData',''))
    if not who: return web.Response(status=401,text='Telegram identity could not be verified')
    uid,name=who; room=ROOMS.get(code)
    if not room or uid not in room['game'].player_ids: return web.Response(status=404,text='Join this room first')
    ws=web.WebSocketResponse(heartbeat=25); await ws.prepare(req); room['sockets'].add((ws,uid)); await _broadcast(room)
    try:
        async for msg in ws:
            if msg.type!=WSMsgType.TEXT: continue
            try: data=json.loads(msg.data); action=data.get('action')
            except Exception: continue
            try:
                async with LOCK:
                    if action=='start':
                        if uid!=room['host']: raise ValueError('Only the host can start the game.')
                        room['game'].start()
                    elif action=='play': room['game'].play(uid,int(data.get('index',-1)),data.get('color'))
                    elif action=='draw': room['game'].draw(uid)
                    elif action=='uno': room['game'].call_uno(uid)
                    elif action=='add_ai': raise ValueError('AI players are not enabled in online rooms yet.')
                    else: raise ValueError('Unknown action.')
                await _broadcast(room)
            except (ValueError,TypeError) as e: await ws.send_json({'type':'error','message':str(e)})
    finally:
        room['sockets'].discard((ws,uid))
    return ws
async def start_server():
    app=web.Application(client_max_size=1024*1024)
    app.router.add_get('/',index); app.router.add_get('/health',health); app.router.add_post('/api/rooms',create_room)
    app.router.add_post('/api/rooms/{code}/join',join_room); app.router.add_get('/api/rooms/{code}',room_info); app.router.add_get('/ws/{code}',websocket)
    app.router.add_static('/static/',str(WEB),show_index=False)
    runner=web.AppRunner(app); await runner.setup(); port=int(os.getenv('PORT','8080')); site=web.TCPSite(runner,'0.0.0.0',port); await site.start()
    print(f'[UNO] Web server listening on 0.0.0.0:{port}',flush=True)
    return runner
