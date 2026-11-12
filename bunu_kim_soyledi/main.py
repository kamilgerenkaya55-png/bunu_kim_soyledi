import json
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from network_utils import get_local_ip, generate_qr_base64, print_terminal_qr
from game_manager import game_manager

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Bunu Kim Söyledi?")

# Statik ve şablon dizinleri
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

PORT = 8000
LOCAL_IP = get_local_ip()
JOIN_URL = f"http://{LOCAL_IP}:{PORT}"

@app.get("/", response_class=HTMLResponse)
async def player_page(request: Request):
    """Oyuncuların telefonlarından katıldığı sayfa."""
    return templates.TemplateResponse(
        request=request,
        name="player.html",
        context={
            "join_url": JOIN_URL,
            "local_ip": LOCAL_IP
        }
    )

@app.get("/host", response_class=HTMLResponse)
async def host_page(request: Request):
    """Bilgisayar / TV ekranı için büyük oyun sunucusu ekranı."""
    qr_b64 = generate_qr_base64(JOIN_URL)
    return templates.TemplateResponse(
        request=request,
        name="host.html",
        context={
            "join_url": JOIN_URL,
            "local_ip": LOCAL_IP,
            "qr_code": qr_b64
        }
    )

@app.get("/api/info")
async def get_network_info():
    """Bağlantı ve QR kod bilgilerini döner."""
    return {
        "local_ip": LOCAL_IP,
        "port": PORT,
        "join_url": JOIN_URL,
        "qr_code": generate_qr_base64(JOIN_URL)
    }

# ==================== WEBSOCKET BAĞLANTILARI ====================

@app.websocket("/ws/host")
async def websocket_host(websocket: WebSocket):
    """Host ekranının bağlandığı WebSocket."""
    await websocket.accept()
    await game_manager.register_host(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "start_game":
                success, msg = await game_manager.start_game()
                if not success:
                    await websocket.send_json({"type": "error", "message": msg})
            elif action == "next_round":
                await game_manager.next_secret()
            elif action == "reset_game":
                await game_manager.reset_to_lobby()
            elif action == "trigger_reveal":
                await game_manager.reveal_round()
                
    except WebSocketDisconnect:
        await game_manager.unregister_host()
    except Exception as e:
        print(f"Host WS Hatası: {e}")
        await game_manager.unregister_host()

@app.websocket("/ws/player/{player_id}")
async def websocket_player(websocket: WebSocket, player_id: str):
    """Oyuncunun telefonundan bağlandığı WebSocket."""
    await websocket.accept()
    player = None
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "join":
                name = data.get("name", "Misafir")
                avatar = data.get("avatar", "🦊")
                player = await game_manager.add_player(player_id, name, avatar, websocket)
                await websocket.send_json({
                    "type": "joined_success",
                    "player": player.to_dict(),
                    "state": game_manager.state
                })
                
            elif action == "submit_secret":
                secret = data.get("secret", "")
                await game_manager.submit_secret(player_id, secret)
                
            elif action == "vote":
                guessed_id = data.get("guessed_player_id")
                await game_manager.vote(player_id, guessed_id)
                
            elif action == "chat":
                text = data.get("text", "")
                if player and text.strip():
                    await game_manager.add_chat_message(player.name, player.avatar, text.strip())
                    
            elif action == "reaction":
                emoji = data.get("emoji", "🔥")
                if player:
                    await game_manager.send_reaction(player.name, emoji)
                    
    except WebSocketDisconnect:
        if player:
            await game_manager.remove_player(player_id)
    except Exception as e:
        print(f"Player WS Hatası: {e}")
        if player:
            await game_manager.remove_player(player_id)

def start_server():
    print("\n" + "="*50)
    print("🎮 BUNU KİM SÖYLEDİ? - OYUN SUNUCUSU BAŞLATILIYOR")
    print("="*50)
    print(f"📡 Wi-Fi IP Adresi : {LOCAL_IP}")
    print(f"🔗 Telefon Bağlantı: {JOIN_URL}")
    print(f"🖥️  Host Ekranı    : http://localhost:{PORT}/host")
    print("\n📲 Telefonunuzdan katılmak için aşağıdaki QR Kodu okutabilirsiniz:")
    print_terminal_qr(JOIN_URL)
    print("="*50 + "\n")
    
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)

if __name__ == "__main__":
    start_server()
